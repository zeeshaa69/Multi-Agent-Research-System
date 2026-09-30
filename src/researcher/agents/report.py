"""Report Writer: assemble, validate and render the final structured report."""

from __future__ import annotations

from ..errors import PermanentError
from ..models import Job, Report, ReportStatement, TaskRecord
from .base import Agent, JobContext
from .citations import validate_report

LABELS = {
    "source_supported": "Source-supported",
    "uncertain": "Uncertain",
    "conflicting": "Conflicting",
    "generated_synthesis": "Generated synthesis",
}


def build_limitations(job: Job, llm_name: str | None) -> list[str]:
    out: list[str] = []
    if any(s.source_type == "fixture" for s in job.sources):
        out.append(
            "Sources are synthetic fixture documents used for testing; "
            "they are not real research findings."
        )
    if llm_name:
        out.append(
            f"Claims and the overview may have been drafted with the local model "
            f"{llm_name}; generated-synthesis statements are not source-verified."
        )
    else:
        out.append("Claims were extracted with rule-based heuristics; no language model was used.")
    out.append(
        "Agreement and conflict detection compares wording, numbers and negation; "
        "semantic contradictions expressed differently can be missed."
    )
    out.extend(job.warnings)
    return out


def render_markdown(report: Report, job: Job) -> str:
    index = {sid: i for i, sid in enumerate(report.source_ids, start=1)}

    def cite(st: ReportStatement) -> str:
        return "".join(f" [S{index[s]}]" for s in st.source_ids if s in index)

    def line(st: ReportStatement) -> str:
        conf = f" (confidence {st.confidence:.2f})" if st.confidence is not None else ""
        return f"- **[{LABELS[st.kind]}]** {st.text}{cite(st)}{conf}"

    out = ["# Research report", "", f"**Question:** {report.question}", "", "## Overview", ""]
    out += [line(s) for s in report.summary]
    for sec in report.sections:
        out += ["", f"## {sec.title}", ""]
        out += [line(s) for s in sec.statements] or ["- _No usable evidence was found._"]
    out += ["", "## Sources", ""]
    for sid, i in index.items():
        src = job.source_by_id(sid)
        if src:
            out.append(
                f"- [S{i}] {src.title} — {src.url} "
                f"(retrieved {src.retrieved_at:%Y-%m-%d %H:%M} UTC, sha256 {src.content_hash[:12]})"
            )
    out += ["", "## Limitations", ""] + [f"- {item}" for item in report.limitations]
    return "\n".join(out) + "\n"


class ReportWriterAgent(Agent):
    name = "report_writer"
    kind = "write_report"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job = ctx.job
        draft = job.draft
        if draft is None:
            raise PermanentError("no synthesis draft available")
        statements = list(draft.summary) + [s for sec in draft.sections for s in sec.statements]
        cited = list(dict.fromkeys(sid for s in statements for sid in s.source_ids))
        kinds = [s.kind for s in statements]
        claim_counts = {
            k: sum(1 for c in job.claims if c.verification_status == k)
            for k in ("supported", "uncertain", "conflicting", "unsupported")
        }
        stats = {
            "subquestions": len(draft.sections),
            "unanswered_subquestions": sum(1 for s in draft.sections if s.unanswered),
            "sources_retrieved": len(job.sources),
            "sources_cited": len(cited),
            "claims_total": len(job.claims),
            **{f"claims_{k}": v for k, v in claim_counts.items()},
            **{
                f"statements_{k}": kinds.count(k)
                for k in ("source_supported", "uncertain", "conflicting", "generated_synthesis")
            },
        }
        llm = ctx.services.llm
        report = draft.model_copy(
            update={
                "source_ids": cited,
                "stats": stats,
                "limitations": build_limitations(job, llm.name if llm else None),
                "generated_at": ctx.services.clock(),
            }
        )
        problems = validate_report(report, job.claims, job.sources)
        if problems:
            for p in problems:
                ctx.log(self.name, "report_invalid", p, level="error", task_id=task.id)
            raise PermanentError(f"report failed citation validation: {problems[0]}")
        report.markdown = render_markdown(report, job)
        job.report = report
        ctx.log(
            self.name,
            "report_written",
            "final report validated and written",
            task_id=task.id,
            stats=stats,
        )
