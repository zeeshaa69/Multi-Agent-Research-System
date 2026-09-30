"""Synthesis Agent: combine verified claims into report sections.

Source-backed statements reuse claim text and quotes verbatim. The only free text is
the overview, which is always labelled ``generated_synthesis``.
"""

from __future__ import annotations

from ..errors import ModelOutputError
from ..llm import parse_json_response
from ..models import (
    Claim,
    Job,
    Report,
    ReportSection,
    ReportStatement,
    StatementKind,
    TaskRecord,
    short_id,
)
from ..textutil import numbers
from .base import Agent, JobContext

KIND_BY_STATUS: dict[str, StatementKind] = {
    "supported": "source_supported",
    "uncertain": "uncertain",
    "conflicting": "conflicting",
}


def _primary_subquestion(claim: Claim, order: list[str]) -> str | None:
    for sq_id in claim.subquestion_ids:
        if sq_id in order:
            return sq_id
    return None


def build_sections(job: Job) -> tuple[list[ReportSection], list[str]]:
    order = [q.id for q in job.subquestions]
    sections = {q.id: ReportSection(subquestion_id=q.id, title=q.text) for q in job.subquestions}
    excluded: list[str] = []
    member_to_claim = {ref.claim_id: c.id for c in job.claims for ref in c.supporting_sources}
    emitted_conflicts: set[tuple[str, ...]] = set()
    for claim in sorted(
        job.claims,
        key=lambda c: (
            order.index(c.subquestion_ids[0])
            if c.subquestion_ids and c.subquestion_ids[0] in order
            else 99,
            c.id,
        ),
    ):
        sq_id = _primary_subquestion(claim, order)
        if claim.verification_status == "unsupported" or sq_id is None:
            excluded.append(claim.id)
            continue
        section = sections[sq_id]
        if claim.verification_status == "conflicting":
            others = {member_to_claim.get(e.claim_id) for e in claim.conflicting_evidence}
            involved = tuple(sorted({claim.id} | {o for o in others if o}))
            if involved in emitted_conflicts:
                continue
            emitted_conflicts.add(involved)
            ref = claim.supporting_sources[0]
            parts = [f"“{ref.quote}”"] + [f"“{e.quote}”" for e in claim.conflicting_evidence[:3]]
            reasons = "; ".join(sorted({e.reason for e in claim.conflicting_evidence}))
            text = "Sources disagree: " + " versus ".join(parts) + f" ({reasons})."
            source_ids = sorted(
                {r.source_id for r in claim.supporting_sources}
                | {e.source_id for e in claim.conflicting_evidence}
            )
            section.statements.append(
                ReportStatement(
                    id=short_id("st", *involved),
                    text=text,
                    kind="conflicting",
                    claim_ids=list(involved),
                    source_ids=source_ids,
                    confidence=claim.confidence,
                )
            )
            continue
        section.statements.append(
            ReportStatement(
                id=short_id("st", claim.id),
                text=claim.claim,
                kind=KIND_BY_STATUS[claim.verification_status],
                claim_ids=[claim.id],
                source_ids=sorted({r.source_id for r in claim.supporting_sources}),
                confidence=claim.confidence,
            )
        )
    for section in sections.values():
        section.unanswered = not section.statements
    return [sections[i] for i in order], excluded


def template_summary(job: Job, sections: list[ReportSection]) -> list[ReportStatement]:
    stmts = [st for sec in sections for st in sec.statements]
    n = {k: sum(1 for s in stmts if s.kind == k) for k in KIND_BY_STATUS.values()}
    cited = {sid for s in stmts for sid in s.source_ids}
    lines = [
        f"This report covers {len(sections)} sub-questions using {len(cited)} cited sources. "
        f"Statements by status: source-supported {n['source_supported']}, "
        f"uncertain {n['uncertain']}, conflicting {n['conflicting']}."
    ]
    unanswered = [sec.title for sec in sections if sec.unanswered]
    if unanswered:
        lines.append("No usable evidence was found for: " + "; ".join(unanswered) + ".")
    if n["conflicting"]:
        lines.append(
            "Sources conflict on at least one point; check the conflicting statements "
            "before relying on the affected figures."
        )
    return [
        ReportStatement(id=short_id("sum", str(i), line), text=line, kind="generated_synthesis")
        for i, line in enumerate(lines)
    ]


def parse_llm_summary(raw: str, job: Job, sections: list[ReportSection]) -> ReportStatement:
    """Accept a model-written overview only if it cites real claims and adds no new numbers."""
    data = parse_json_response(raw)
    if not isinstance(data, dict) or not isinstance(data.get("summary"), str):
        raise ModelOutputError("summary JSON missing 'summary'")
    known = {cid for sec in sections for st in sec.statements for cid in st.claim_ids}
    ids = [c for c in data.get("claim_ids", []) if isinstance(c, str) and c in known]
    if not ids:
        raise ModelOutputError("summary cites no known claims")
    summary = " ".join(data["summary"].split())
    allowed: set[float] = set()
    for cid in ids:
        claim = job.claim_by_id(cid)
        if claim:
            allowed |= numbers(claim.claim)
    if not numbers(summary) <= allowed:
        raise ModelOutputError("summary contains numbers absent from the cited claims")
    source_ids = sorted(
        {
            sid
            for sec in sections
            for st in sec.statements
            if set(st.claim_ids) & set(ids)
            for sid in st.source_ids
        }
    )
    return ReportStatement(
        id=short_id("sum", "llm", summary),
        text=summary,
        kind="generated_synthesis",
        claim_ids=ids,
        source_ids=source_ids,
    )


class SynthesisAgent(Agent):
    name = "synthesizer"
    kind = "synthesize"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job = ctx.job
        sections, excluded = build_sections(job)
        summary = template_summary(job, sections)
        llm = ctx.services.llm
        if llm is not None and any(sec.statements for sec in sections):
            listing = "\n".join(
                f"[{cid}] ({st.kind}) {st.text}"
                for sec in sections
                for st in sec.statements
                for cid in st.claim_ids[:1]
                if st.kind != "conflicting"
            )
            prompt = (
                f"Question: {job.question}\nVerified statements:\n{listing}\n\n"
                "Write a 2-3 sentence overview that uses only these statements. Do not add facts "
                "or numbers. Mention uncertainty where a statement is uncertain.\n"
                'Reply with JSON only: {"summary": "...", "claim_ids": ["..."]}'
            )
            raw = await llm.complete(prompt, system="You summarise verified findings faithfully.")
            try:
                summary.insert(0, parse_llm_summary(raw, job, sections))
                ctx.log(
                    self.name, "summary_llm", f"overview drafted by {llm.name}", task_id=task.id
                )
            except ModelOutputError as exc:
                ctx.log(
                    self.name,
                    "summary_fallback",
                    f"model overview rejected ({exc})",
                    level="warning",
                    task_id=task.id,
                )
        job.draft = Report(
            job_id=job.id,
            question=job.question,
            generated_at=ctx.services.clock(),
            summary=summary,
            sections=sections,
            excluded_claim_ids=excluded,
        )
        ctx.log(
            self.name,
            "synthesized",
            f"{sum(len(s.statements) for s in sections)} statements, "
            f"{len(excluded)} claims excluded",
            task_id=task.id,
        )
