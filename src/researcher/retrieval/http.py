"""Guarded public-HTTP fetching: scheme allow-list, SSRF checks, robots.txt, size cap."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..errors import PermanentError, TransientError
from .base import Document
from .html import html_to_text

MAX_REDIRECTS = 3


async def _resolves_to_public(host: str) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise TransientError(f"cannot resolve {host}: {exc}") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            return False
    return True


class HttpFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        max_bytes: int,
        allow_private_hosts: bool = False,
        respect_robots: bool = True,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._ua = user_agent
        self._max_bytes = max_bytes
        self._allow_private = allow_private_hosts
        self._respect_robots = respect_robots
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._robots: dict[str, RobotFileParser | None] = {}

    async def check_url(self, url: str) -> None:
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise PermanentError(f"only http(s) URLs are allowed: {url}")
        if not self._allow_private and not await _resolves_to_public(parts.hostname):
            raise PermanentError(f"refusing to fetch non-public address: {parts.hostname}")

    async def _robots_allows(self, url: str) -> bool:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                resp = await self._client.get(
                    f"{origin}/robots.txt", headers={"User-Agent": self._ua}
                )
                if resp.status_code == 200 and parser is not None:
                    parser.parse(resp.text.splitlines())
                elif resp.status_code in (401, 403) and parser is not None:
                    parser.parse(["User-agent: *", "Disallow: /"])
                else:
                    parser = None  # no robots.txt: everything allowed
            except httpx.HTTPError:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(self._ua, url)

    async def fetch(self, url: str) -> Document:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await self.check_url(current)
            if self._respect_robots and not await self._robots_allows(current):
                raise PermanentError(f"blocked by robots.txt: {current}")
            try:
                async with self._client.stream(
                    "GET", current, headers={"User-Agent": self._ua}
                ) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise PermanentError("redirect without Location header")
                        current = urljoin(current, location)
                        continue
                    if resp.status_code >= 500 or resp.status_code == 429:
                        raise TransientError(f"HTTP {resp.status_code} from {current}")
                    if resp.status_code >= 400:
                        raise PermanentError(f"HTTP {resp.status_code} from {current}")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in ("text/html", "text/plain", "application/xhtml+xml"):
                        raise PermanentError(f"unsupported content type {ctype!r}")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            break
                    raw = bytes(body[: self._max_bytes]).decode(
                        resp.encoding or "utf-8", errors="replace"
                    )
            except httpx.HTTPError as exc:
                raise TransientError(f"request to {current} failed: {exc}") from exc
            if ctype == "text/plain":
                title, text = current, raw
            else:
                title, text = html_to_text(raw)
            return Document(url=current, title=title or current, text=text, source_type="web")
        raise PermanentError(f"too many redirects for {url}")
