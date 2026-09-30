"""Retrieval interface: search for candidate documents, then fetch their text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import SourceType


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    source_type: SourceType
    snippet: str = ""


@dataclass(frozen=True)
class Document:
    url: str
    title: str
    text: str
    source_type: SourceType


class Retriever(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[SearchHit]: ...

    async def fetch(self, hit: SearchHit) -> Document: ...

    async def fetch_url(self, url: str) -> Document: ...
