"""Research Agent: find and fetch documents for one sub-question."""

from __future__ import annotations

import asyncio

from ..errors import PermanentError, TransientError
from ..models import Source, TaskRecord, content_hash
from ..retrieval import Document, SearchHit
from .base import Agent, JobContext

FETCH_CONCURRENCY = 4


class ResearchAgent(Agent):
    name = "researcher"
    kind = "research"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job = ctx.job
        sq = job.subquestion_by_id(task.payload["subquestion_id"])
        if sq is None:
            raise PermanentError(f"unknown sub-question {task.payload.get('subquestion_id')}")
        retriever = ctx.services.retriever
        hits = await retriever.search(sq.text, job.options.sources_per_subquestion)
        ctx.log(
            self.name,
            "search",
            f"{len(hits)} candidate documents for {sq.id}",
            task_id=task.id,
            query=sq.text,
            urls=[h.url for h in hits],
        )

        targets: list[tuple[str, SearchHit | None]] = [(h.url, h) for h in hits]
        if job.subquestions and sq.id == job.subquestions[0].id:
            known = {u for u, _ in targets}
            targets += [(u, None) for u in job.options.seed_urls if u not in known]

        sem = asyncio.Semaphore(FETCH_CONCURRENCY)

        async def fetch(url: str, hit: SearchHit | None) -> Document | Exception:
            async with sem:
                try:
                    return await (retriever.fetch(hit) if hit else retriever.fetch_url(url))
                except (TransientError, PermanentError) as exc:
                    return exc

        results = await asyncio.gather(*(fetch(u, h) for u, h in targets))
        docs: list[Document] = []
        transient: list[Exception] = []
        for (url, _), res in zip(targets, results, strict=True):
            if isinstance(res, Document):
                docs.append(res)
                continue
            ctx.log(
                self.name,
                "fetch_failed",
                f"could not fetch {url}: {res}",
                level="warning",
                task_id=task.id,
                url=url,
            )
            if isinstance(res, TransientError):
                transient.append(res)
        if targets and not docs and transient:
            raise TransientError(f"all fetches failed transiently: {transient[0]}")

        added = 0
        for doc in sorted(docs, key=lambda d: d.url):
            text = doc.text[: ctx.services.settings.max_source_chars]
            digest = content_hash(text)
            existing = next((s for s in job.sources if s.content_hash == digest), None)
            if existing:
                if sq.id not in existing.subquestion_ids:
                    existing.subquestion_ids.append(sq.id)
                ctx.log(
                    self.name,
                    "duplicate_source",
                    f"{doc.url} duplicates {existing.url}",
                    task_id=task.id,
                )
                continue
            job.sources.append(
                Source(
                    id=f"src_{digest[:10]}",
                    url=doc.url,
                    title=doc.title,
                    retrieved_at=ctx.services.clock(),
                    text=text,
                    source_type=doc.source_type,
                    content_hash=digest,
                    subquestion_ids=[sq.id],
                )
            )
            added += 1
        if not docs:
            ctx.log(
                self.name,
                "no_sources",
                f"no documents retrieved for {sq.id}",
                level="warning",
                task_id=task.id,
            )
        ctx.log(
            self.name, "research_done", f"{added} new sources stored for {sq.id}", task_id=task.id
        )
