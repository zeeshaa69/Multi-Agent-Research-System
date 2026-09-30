"""Live retriever: Wikipedia's public MediaWiki API for search, guarded HTTP for other URLs."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlparse

import httpx

from ..errors import PermanentError, TransientError
from .base import Document, SearchHit
from .http import HttpFetcher

API = "https://en.wikipedia.org/w/api.php"


class LiveRetriever:
    """Searches Wikipedia; fetches arbitrary user-supplied URLs via :class:`HttpFetcher`."""

    name = "live"

    def __init__(
        self, fetcher: HttpFetcher, user_agent: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._fetcher = fetcher
        self._headers = {"User-Agent": user_agent}
        self._client = client or httpx.AsyncClient(timeout=20.0)

    async def _api(self, params: dict[str, str]) -> dict[str, object]:
        try:
            resp = await self._client.get(
                API, params={**params, "format": "json"}, headers=self._headers
            )
            if resp.status_code >= 500 or resp.status_code == 429:
                raise TransientError(f"Wikipedia API HTTP {resp.status_code}")
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            return data
        except httpx.HTTPError as exc:
            raise TransientError(f"Wikipedia API request failed: {exc}") from exc

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        data = await self._api(
            {"action": "query", "list": "search", "srsearch": query, "srlimit": str(limit)}
        )
        results = data.get("query", {})
        hits = results.get("search", []) if isinstance(results, dict) else []
        return [
            SearchHit(
                url=f"https://en.wikipedia.org/wiki/{quote(item['title'].replace(' ', '_'))}",
                title=item["title"],
                source_type="encyclopedia",
            )
            for item in hits
        ]

    async def fetch(self, hit: SearchHit) -> Document:
        return await self.fetch_url(hit.url)

    async def fetch_url(self, url: str) -> Document:
        parts = urlparse(url)
        if parts.hostname == "en.wikipedia.org" and parts.path.startswith("/wiki/"):
            title = unquote(parts.path[len("/wiki/") :]).replace("_", " ")
            data = await self._api(
                {"action": "query", "prop": "extracts", "explaintext": "1", "titles": title}
            )
            pages = data.get("query", {})
            page_map = pages.get("pages", {}) if isinstance(pages, dict) else {}
            for page in page_map.values():
                text = page.get("extract", "")
                if text:
                    return Document(
                        url=url,
                        title=page.get("title", title),
                        text=text,
                        source_type="encyclopedia",
                    )
            raise PermanentError(f"Wikipedia page has no text: {title}")
        doc = await self._fetcher.fetch(url)
        return Document(url=doc.url, title=doc.title, text=doc.text, source_type="user_supplied")
