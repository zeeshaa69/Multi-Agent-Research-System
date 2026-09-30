"""Citation Validator: every claim and report statement must trace back to stored evidence."""

from __future__ import annotations

from ..errors import PermanentError
from ..models import CitationIssue, Claim, Job, Report, Source, TaskRecord, content_hash
from ..textutil import locate_quote
from .base import Agent, JobContext


def validate_claims(claims: list[Claim], sources: list[Source]) -> list[CitationIssue]:
    """Drop citations that do not resolve; demote claims left with none. Mutates ``claims``."""
    by_id = {s.id: s for s in sources}
    issues: list[CitationIssue] = []

    def check(claim_id: str, source_id: str, quote: str) -> bool:
        src = by_id.get(source_id)
        if src is None:
            issues.append(
                CitationIssue(
                    claim_id=claim_id, source_id=source_id, problem="source does not exist"
                )
            )
        elif content_hash(src.text) != src.content_hash:
            issues.append(
                CitationIssue(
                    claim_id=claim_id,
                    source_id=source_id,
                    problem="source text does not match its content hash",
                )
            )
        elif locate_quote(quote, src.text) == "none":
            issues.append(
                CitationIssue(
                    claim_id=claim_id, source_id=source_id, problem="quote not found in source text"
                )
            )
        else:
            return True
        return False

    for claim in claims:
        claim.supporting_sources = [
            r for r in claim.supporting_sources if check(claim.id, r.source_id, r.quote)
        ]
        claim.conflicting_evidence = [
            e for e in claim.conflicting_evidence if check(claim.id, e.source_id, e.quote)
        ]
        if not claim.supporting_sources and claim.verification_status != "unsupported":
            claim.verification_status = "unsupported"
            claim.confidence = 0.0
            claim.notes.append("no valid citation remained after validation")
        elif claim.verification_status == "conflicting" and not claim.conflicting_evidence:
            claim.verification_status = "supported"
            claim.notes.append("conflicting citations were invalid and dropped")
    return issues


def validate_report(report: Report, claims: list[Claim], sources: list[Source]) -> list[str]:
    """Check a finished report. Returns human-readable problems (empty list means valid)."""
    claim_map = {c.id: c for c in claims}
    source_ids = {s.id for s in sources}
    problems: list[str] = []
    statements = list(report.summary) + [st for sec in report.sections for st in sec.statements]
    for st in statements:
        for cid in st.claim_ids:
            claim = claim_map.get(cid)
            if claim is None:
                problems.append(f"statement {st.id} cites unknown claim {cid}")
            elif claim.verification_status == "unsupported":
                problems.append(f"statement {st.id} cites unsupported claim {cid}")
        for sid in st.source_ids:
            if sid not in source_ids:
                problems.append(f"statement {st.id} cites unknown source {sid}")
        if st.kind != "generated_synthesis":
            if not st.claim_ids:
                problems.append(f"statement {st.id} ({st.kind}) has no claim")
            if not st.source_ids:
                problems.append(f"statement {st.id} ({st.kind}) has no source")
            for cid in st.claim_ids:
                claim = claim_map.get(cid)
                if claim is not None and not _kind_matches(st.kind, claim):
                    problems.append(
                        f"statement {st.id} is {st.kind} but claim {cid} is "
                        f"{claim.verification_status}"
                    )
    return problems


def _kind_matches(kind: str, claim: Claim) -> bool:
    expected = {
        "supported": "source_supported",
        "uncertain": "uncertain",
        "conflicting": "conflicting",
    }
    return expected.get(claim.verification_status) == kind


class CitationValidatorAgent(Agent):
    name = "citation_validator"
    kind = "validate_citations"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job: Job = ctx.job
        job.citation_issues = validate_claims(job.claims, job.sources)
        for issue in job.citation_issues:
            ctx.log(
                self.name,
                "citation_issue",
                f"{issue.problem} ({issue.source_id})",
                level="warning",
                task_id=task.id,
                claim_id=issue.claim_id,
            )
        cited = sum(1 for c in job.claims if c.supporting_sources)
        ctx.log(
            self.name,
            "citations_validated",
            f"{cited}/{len(job.claims)} claims have valid citations; "
            f"{len(job.citation_issues)} issues",
            task_id=task.id,
        )
        if not job.claims:
            return
        if not any(c.supporting_sources for c in job.claims):
            raise PermanentError("no claim has a valid citation")
