from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from researcher.config import RetryConfig, Settings
from researcher.models import Job, JobOptions, Source, content_hash
from researcher.orchestration import AgentRouter, run_job
from researcher.services import Services, build_services

FIXED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
COST_RISK_Q = "What are the costs, risks and environmental effects of the Harborview Tidal Pilot?"
FULL_Q = (
    "What is the Harborview Tidal Pilot, how much power does it produce, and what does it cost?"
)


class ScriptedLLM:
    """Stand-in model that returns canned text chosen by a callback."""

    name = "scripted"

    def __init__(self, respond: Callable[[str], str]) -> None:
        self.respond = respond
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, system: str = "") -> str:
        self.prompts.append(prompt)
        return self.respond(prompt)


async def no_sleep(_: float) -> None:
    await asyncio.sleep(0)


def make_services(tmp_path: Path, llm: ScriptedLLM | None = None, **overrides: object) -> Services:
    settings = Settings(
        db_path=tmp_path / "h.sqlite3", retry=RetryConfig(base_delay=0.0), **overrides
    )  # type: ignore[arg-type]
    services = build_services(settings)
    services.clock = lambda: FIXED
    services.sleep = no_sleep
    services.llm = llm
    return services


def new_job(question: str, services: Services, options: JobOptions | None = None) -> Job:
    return Job(
        id=uuid.uuid4().hex[:8],
        question=question,
        mode=services.settings.mode,
        created_at=FIXED,
        updated_at=FIXED,
        options=options or JobOptions(),
    )


async def run_offline(question: str, services: Services, router: AgentRouter | None = None) -> Job:
    return await run_job(new_job(question, services), services, router=router)


def make_source(sid: str, text: str, url: str | None = None) -> Source:
    return Source(
        id=sid,
        url=url or f"fixture://t/{sid}",
        title=f"Doc {sid}",
        retrieved_at=FIXED,
        text=text,
        source_type="fixture",
        content_hash=content_hash(text),
    )


@pytest.fixture
def services(tmp_path: Path) -> Services:
    return make_services(tmp_path)
