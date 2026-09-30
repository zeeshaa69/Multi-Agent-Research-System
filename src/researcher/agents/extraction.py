"""Extraction Agent: pull claims, each with a verbatim evidence quote, out of sources."""

from __future__ import annotations

from ..errors import ModelOutputError, PermanentError
from ..llm import parse_json_response
from ..models import ExtractedClaim, Source, SubQuestion, TaskRecord, short_id
from ..textutil import content_tokens, is_hedged, locate_quote, normalize_ws, split_sentences, stem
from .base import Agent, JobContext

MIN_WORDS, MAX_WORDS = 5, 60
MIN_OVERLAP = 1.5
MAX_CLAIMS_PER_SOURCE = 8
LLM_TEXT_LIMIT = 6000


def heuristic_extract(
    source: Source, sq: SubQuestion, topic: frozenset[str] = frozenset()
) -> list[ExtractedClaim]:
    """Pick sentences that overlap the sub-question. ``topic`` tokens (shared by every
    sub-question) count half, so a bare mention of the subject is not enough."""
    wanted = content_tokens(sq.text) | {stem(k) for k in sq.keywords}
    scored: list[tuple[float, int, ExtractedClaim]] = []
    for idx, span in enumerate(split_sentences(source.text)):
        n_words = len(span.text.split())
        if span.text.endswith("?") or not MIN_WORDS <= n_words <= MAX_WORDS:
            continue
        overlap = wanted & content_tokens(span.text)
        score = sum(0.5 if t in topic else 1.0 for t in overlap)
        if score < MIN_OVERLAP:
            continue
        text = normalize_ws(span.text)
        claim = ExtractedClaim(
            id=short_id("clm", source.content_hash, text),
            text=text,
            quote=span.text,
            relevance={sq.id: score},
            hedged=is_hedged(text),
        )
        scored.append((-score, idx, claim))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [c for _, _, c in scored[:MAX_CLAIMS_PER_SOURCE]]


def parse_llm_claims(raw: str, source: Source, sq: SubQuestion) -> tuple[list[ExtractedClaim], int]:
    """Validate model output. Returns (claims, rejected_count). Quotes must occur in the source."""
    data = parse_json_response(raw)
    items = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ModelOutputError("extraction JSON has no 'claims' list")
    claims: list[ExtractedClaim] = []
    rejected = 0
    for item in items:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("claim"), str)
            and isinstance(item.get("quote"), str)
        ):
            rejected += 1
            continue
        text, quote = normalize_ws(item["claim"]), item["quote"].strip()
        if not text or locate_quote(quote, source.text) == "none":
            rejected += 1
            continue
        claims.append(
            ExtractedClaim(
                id=short_id("clm", source.content_hash, text),
                text=text,
                quote=quote,
                relevance={sq.id: 1.0},
                hedged=is_hedged(text) or is_hedged(quote),
            )
        )
    return claims[:MAX_CLAIMS_PER_SOURCE], rejected


class ExtractionAgent(Agent):
    name = "extractor"
    kind = "extract"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job = ctx.job
        sq = job.subquestion_by_id(task.payload["subquestion_id"])
        if sq is None:
            raise PermanentError(f"unknown sub-question {task.payload.get('subquestion_id')}")
        llm = ctx.services.llm
        topic: frozenset[str] = frozenset()
        if len(job.subquestions) > 1:
            topic = frozenset(set.intersection(*(content_tokens(q.text) for q in job.subquestions)))
        total = 0
        for source in [s for s in job.sources if sq.id in s.subquestion_ids]:
            claims: list[ExtractedClaim] | None = None
            if llm is not None:
                prompt = (
                    f"Sub-question: {sq.text}\n"
                    "Extract factual claims from the document that help answer it. For each claim "
                    "give an exact quote copied word for word from the document.\n"
                    'Reply with JSON only: {"claims": [{"claim": "...", "quote": "..."}]}\n\n'
                    f"Document ({source.title}):\n{source.text[:LLM_TEXT_LIMIT]}"
                )
                raw = await llm.complete(prompt, system="You extract claims without adding facts.")
                try:
                    claims, rejected = parse_llm_claims(raw, source, sq)
                    if rejected:
                        ctx.log(
                            self.name,
                            "claims_rejected",
                            f"{rejected} model claims dropped: quote not found in {source.id}",
                            level="warning",
                            task_id=task.id,
                        )
                except ModelOutputError as exc:
                    ctx.log(
                        self.name,
                        "extract_fallback",
                        f"model output rejected for {source.id} ({exc}); using rules",
                        level="warning",
                        task_id=task.id,
                    )
            if claims is None:
                claims = heuristic_extract(source, sq, topic)
            by_id = {c.id: c for c in source.claims}
            for claim in claims:
                prior = by_id.get(claim.id)
                if prior:
                    prior.relevance.update(claim.relevance)
                else:
                    source.claims.append(claim)
                    by_id[claim.id] = claim
            total += len(claims)
            ctx.log(
                self.name,
                "extracted",
                f"{len(claims)} claims from {source.id} for {sq.id}",
                task_id=task.id,
                source_id=source.id,
            )
        ctx.log(self.name, "extract_done", f"{total} claims extracted for {sq.id}", task_id=task.id)
