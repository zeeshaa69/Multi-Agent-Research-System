"""Interface for local language-model backends."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from ..errors import ModelOutputError


class LLMClient(Protocol):
    name: str

    async def complete(self, prompt: str, *, system: str = "") -> str: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_response(raw: str) -> Any:
    """Parse model output as JSON, tolerating code fences and surrounding prose.

    Raises ModelOutputError; agents decide whether to retry or fall back.
    """
    text = _FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ModelOutputError(f"model did not return valid JSON: {raw[:120]!r}")
