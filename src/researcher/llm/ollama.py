"""Ollama backend (local server, default http://127.0.0.1:11434)."""

from __future__ import annotations

import httpx

from ..errors import TransientError


class OllamaClient:
    def __init__(
        self,
        host: str,
        model: str,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = f"ollama:{model}"
        self._host = host.rstrip("/")
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def complete(self, prompt: str, *, system: str = "") -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            resp = await self._client.post(f"{self._host}/api/generate", json=payload)
            resp.raise_for_status()
            return str(resp.json()["response"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise TransientError(f"ollama request failed: {exc}") from exc
