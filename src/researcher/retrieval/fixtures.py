"""Offline retriever backed by the synthetic fixture corpus (no network)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..errors import PermanentError
from ..textutil import content_tokens
from .base import Document, SearchHit


class FixtureRetriever:
    name = "fixtures"

    def __init__(self, corpus_dir: Path, latency: float = 0.0) -> None:
        self._latency = latency
        self._docs: dict[str, Document] = {}
        self._tokens: dict[str, set[str]] = {}
        for path in sorted(corpus_dir.glob("*.json")):
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            doc = Document(
                url=raw["url"], title=raw["title"], text=raw["text"], source_type="fixture"
            )
            self._docs[doc.url] = doc
            self._tokens[doc.url] = content_tokens(doc.title + " " + doc.text)

    async def _pause(self) -> None:
        if self._latency:
            await asyncio.sleep(self._latency)

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        await self._pause()
        q = content_tokens(query)
        scored = []
        for url, toks in self._tokens.items():
            score = len(q & toks)
            if score >= 2:
                scored.append((-score, url))
        scored.sort()
        return [
            SearchHit(url=u, title=self._docs[u].title, source_type="fixture")
            for _, u in scored[:limit]
        ]

    async def fetch(self, hit: SearchHit) -> Document:
        return await self.fetch_url(hit.url)

    async def fetch_url(self, url: str) -> Document:
        await self._pause()
        try:
            return self._docs[url]
        except KeyError:
            raise PermanentError(f"fixture not found: {url}") from None
