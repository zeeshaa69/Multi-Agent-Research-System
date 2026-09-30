"""llama.cpp server backend (``llama-server``, default http://127.0.0.1:8080)."""

from __future__ import annotations

import httpx

from ..errors import TransientError


class LlamaCppClient:
    def __init__(
        self, host: str, timeout: float = 120.0, client: httpx.AsyncClient | None = None
    ) -> None:
        self.name = "llamacpp"
        self._host = host.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def complete(self, prompt: str, *, system: str = "") -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        payload = {"prompt": full, "temperature": 0, "n_predict": 1024, "stream": False}
        try:
            resp = await self._client.post(f"{self._host}/completion", json=payload)
            resp.raise_for_status()
            return str(resp.json()["content"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise TransientError(f"llama.cpp request failed: {exc}") from exc
