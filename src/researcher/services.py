"""Shared dependencies handed to every agent."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .config import Settings
from .llm import LlamaCppClient, LLMClient, OllamaClient
from .models import utcnow
from .retrieval import FixtureRetriever, HttpFetcher, LiveRetriever, Retriever


@dataclass
class Services:
    settings: Settings
    retriever: Retriever
    llm: LLMClient | None = None
    clock: Callable[[], datetime] = utcnow
    sleep: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)


def build_services(settings: Settings) -> Services:
    retriever: Retriever
    if settings.retrieval == "fixtures":
        retriever = FixtureRetriever(settings.fixtures_dir, settings.simulated_latency)
    else:
        fetcher = HttpFetcher(
            user_agent=settings.user_agent,
            max_bytes=settings.max_fetch_bytes,
            allow_private_hosts=settings.allow_private_hosts,
            respect_robots=settings.respect_robots,
        )
        retriever = LiveRetriever(fetcher, settings.user_agent)
    llm: LLMClient | None = None
    if settings.llm == "ollama":
        llm = OllamaClient(settings.ollama_host, settings.ollama_model, settings.llm_timeout)
    elif settings.llm == "llamacpp":
        llm = LlamaCppClient(settings.llamacpp_host, settings.llm_timeout)
    return Services(settings=settings, retriever=retriever, llm=llm)
