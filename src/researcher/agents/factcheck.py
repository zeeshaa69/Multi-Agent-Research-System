"""Fact Checker: test claims against the evidence actually held in the source store.

Deterministic by design. A claim is only ever as strong as:
  1. its verbatim quote being found in the stored source text,
  2. the claim wording staying faithful to that quote,
  3. how many distinct sources agree, and whether any source contradicts it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import (
    Claim,
    ConflictEvidence,
    ExtractedClaim,
    Source,
    SourceRef,
    TaskRecord,
    short_id,
)
from ..textutil import (
    content_tokens,
    format_number,
    has_negation,
    locate_quote,
    number_units,
    numbers,
    overlap_coefficient,
)
from .base import Agent, JobContext

TOPIC_OVERLAP = 0.6
MIN_SHARED_TOKENS = 3
FAITHFUL_OVERLAP = 0.6
COMMON_TOKEN_MIN_CLAIMS = 5
COMMON_TOKEN_RATIO = 0.4
BASE_CONFIDENCE = {1: 0.55, 2: 0.8}
MULTI_SOURCE_CONFIDENCE = 0.9
UNCERTAIN_FACTOR = 0.6
CONFLICT_CEILING = 0.6


@dataclass
class Member:
    source: Source
    claim: ExtractedClaim


def _figures_conflict(a: str, b: str) -> str | None:
    """Describe a numeric disagreement between two claims, or None if they do not disagree."""
    ua, ub = number_units(a), number_units(b)

    def fmt(vals: set[float]) -> str:
        return ", ".join(format_number(v) for v in sorted(vals))

    for unit in sorted(set(ua) & set(ub) - {""}):
        va, vb = ua[unit], ub[unit]
        if not (va <= vb or vb <= va):
            return f"different figures for '{unit}': {fmt(va)} vs {fmt(vb)}"
    if set(ua) == {""} == set(ub) and len(ua[""]) == 1 and len(ub[""]) == 1 and ua[""] != ub[""]:
        return f"different figures: {fmt(ua[''])} vs {fmt(ub[''])}"
    return None


def relation(a: str, b: str, ignore: frozenset[str] = frozenset()) -> tuple[str, str]:
    """Compare two claim texts. Returns ('agree'|'conflict'|'unrelated', reason).

    ``ignore`` holds tokens too common in the job to signal topical similarity.
    """
    ta, tb = content_tokens(a) - ignore, content_tokens(b) - ignore
    shared = len(ta & tb)
    if (
        shared < min(MIN_SHARED_TOKENS, len(ta), len(tb))
        or overlap_coefficient(ta, tb) < TOPIC_OVERLAP
    ):
        return "unrelated", ""
    reason = _figures_conflict(a, b)
    if reason:
        return "conflict", reason
    if has_negation(a) != has_negation(b):
        return "conflict", "one statement negates the other"
    return "agree", ""


def check_grounding(source: Source, claim: ExtractedClaim) -> str:
    """Independently re-verify an extracted claim against the stored source text."""
    found = locate_quote(claim.quote, source.text)
    if found == "none":
        return "none"
    cq, qq = content_tokens(claim.text), content_tokens(claim.quote)
    if overlap_coefficient(cq, qq) < FAITHFUL_OVERLAP or not numbers(claim.text) <= numbers(
        claim.quote
    ):
        return "none"  # claim wording drifted away from its evidence
    return found


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        self.parent[self.find(i)] = self.find(j)


def _confidence(n_sources: int, n_conflict_sources: int, uncertain: bool) -> float:
    if n_conflict_sources:
        return round(CONFLICT_CEILING * n_sources / (n_sources + n_conflict_sources), 2)
    base = BASE_CONFIDENCE.get(n_sources, MULTI_SOURCE_CONFIDENCE)
    return round(base * UNCERTAIN_FACTOR if uncertain else base, 2)


def check_claims(sources: list[Source]) -> list[Claim]:
    members: list[Member] = []
    unsupported: list[Claim] = []
    for source in sorted(sources, key=lambda s: s.id):
        for ec in sorted(source.claims, key=lambda c: c.id):
            ec.grounding = check_grounding(source, ec)  # type: ignore[assignment]
            if ec.grounding == "none":
                unsupported.append(
                    Claim(
                        id=short_id("cl", ec.id),
                        claim=ec.text,
                        confidence=0.0,
                        verification_status="unsupported",
                        subquestion_ids=sorted(ec.relevance, key=lambda k: (-ec.relevance[k], k)),
                        hedged=ec.hedged,
                        notes=[f"quote or wording not verifiable against {source.id}"],
                    )
                )
            else:
                members.append(Member(source, ec))

    ignore: frozenset[str] = frozenset()
    if len(members) >= COMMON_TOKEN_MIN_CLAIMS:
        df: dict[str, int] = {}
        for m in members:
            for tok in content_tokens(m.claim.text):
                df[tok] = df.get(tok, 0) + 1
        ignore = frozenset(t for t, n in df.items() if n / len(members) >= COMMON_TOKEN_RATIO)

    uf = _UnionFind(len(members))
    conflicts: list[tuple[int, int, str]] = []
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            rel, reason = relation(members[i].claim.text, members[j].claim.text, ignore)
            if rel == "agree":
                uf.union(i, j)
            elif rel == "conflict":
                conflicts.append((i, j, reason))

    groups: dict[int, list[int]] = {}
    for i in range(len(members)):
        groups.setdefault(uf.find(i), []).append(i)

    claims: list[Claim] = []
    for root in sorted(groups, key=lambda r: min(groups[r])):
        idxs = groups[root]
        ordered = sorted(
            idxs, key=lambda i: (members[i].claim.hedged, members[i].source.id, members[i].claim.id)
        )
        head = members[ordered[0]]
        refs: list[SourceRef] = []
        seen_sources: set[str] = set()
        for i in ordered:
            m = members[i]
            if m.source.id in seen_sources:
                continue
            seen_sources.add(m.source.id)
            refs.append(SourceRef(source_id=m.source.id, quote=m.claim.quote, claim_id=m.claim.id))
        evidence: list[ConflictEvidence] = []
        for i, j, reason in conflicts:
            for mine, other in ((i, j), (j, i)):
                if mine in idxs:
                    o = members[other]
                    evidence.append(
                        ConflictEvidence(
                            source_id=o.source.id,
                            claim_id=o.claim.id,
                            statement=o.claim.text,
                            quote=o.claim.quote,
                            reason=reason,
                        )
                    )
        evidence = sorted(
            {(e.source_id, e.claim_id): e for e in evidence}.values(),
            key=lambda e: (e.source_id, e.claim_id),
        )
        all_hedged = all(members[i].claim.hedged for i in idxs)
        all_fuzzy = all(members[i].claim.grounding == "fuzzy" for i in idxs)
        uncertain = all_hedged or all_fuzzy
        notes: list[str] = []
        if evidence:
            status = "conflicting"
            notes.append("; ".join(sorted({e.reason for e in evidence})))
        elif uncertain:
            status = "uncertain"
            notes.append(
                "hedged wording in every supporting source"
                if all_hedged
                else "quote matched only after ignoring case/punctuation"
            )
        else:
            status = "supported"
        if len(refs) == 1 and status == "supported":
            notes.append("single source")
        rel_scores: dict[str, float] = {}
        for i in idxs:
            for sq_id, score in members[i].claim.relevance.items():
                rel_scores[sq_id] = max(rel_scores.get(sq_id, 0.0), score)
        claims.append(
            Claim(
                id=short_id("cl", *sorted(members[i].claim.id for i in idxs)),
                claim=head.claim.text,
                supporting_sources=refs,
                confidence=_confidence(len(refs), len({e.source_id for e in evidence}), uncertain),
                verification_status=status,
                conflicting_evidence=evidence,
                subquestion_ids=sorted(rel_scores, key=lambda k: (-rel_scores[k], k)),
                hedged=all_hedged,
                notes=notes,
            )
        )
    return claims + unsupported


class FactCheckerAgent(Agent):
    name = "fact_checker"
    kind = "factcheck"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job = ctx.job
        job.claims = check_claims(job.sources)
        counts: dict[str, int] = {}
        for c in job.claims:
            counts[c.verification_status] = counts.get(c.verification_status, 0) + 1
            if c.verification_status == "conflicting":
                ctx.log(
                    self.name,
                    "conflict",
                    f"conflicting evidence: {c.claim}",
                    level="warning",
                    task_id=task.id,
                    claim_id=c.id,
                    reason="; ".join(c.notes),
                )
        ctx.log(
            self.name,
            "factcheck_done",
            f"checked {len(job.claims)} claims",
            task_id=task.id,
            counts=counts,
        )
