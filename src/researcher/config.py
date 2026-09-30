"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

RetrievalBackend = Literal["fixtures", "live"]
LLMBackend = Literal["none", "ollama", "llamacpp"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 0.5
    factor: float = 2.0
    max_delay: float = 8.0


@dataclass(frozen=True)
class Settings:
    """All tunables. ``offline`` means fixtures + no model: fully deterministic."""

    retrieval: RetrievalBackend = "fixtures"
    llm: LLMBackend = "none"
    fixtures_dir: Path = field(default_factory=lambda: _repo_root() / "fixtures" / "corpus")
    db_path: Path = field(default_factory=lambda: Path("data") / "history.sqlite3")
    frontend_dist: Path = field(default_factory=lambda: _repo_root() / "frontend" / "dist")
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    llamacpp_host: str = "http://127.0.0.1:8080"
    llm_timeout: float = 120.0
    max_workers: int = 4
    max_concurrent_jobs: int = 2
    task_timeout: float = 300.0
    retry: RetryConfig = field(default_factory=RetryConfig)
    simulated_latency: float = 0.0
    max_source_chars: int = 60_000
    max_fetch_bytes: int = 2_000_000
    allow_private_hosts: bool = False
    respect_robots: bool = True
    user_agent: str = "multi-agent-researcher/0.1 (+local research tool)"
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")

    @property
    def mode(self) -> str:
        return "offline" if self.retrieval == "fixtures" and self.llm == "none" else "live"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        defaults = cls()
        retrieval = env.get("RESEARCHER_RETRIEVAL", defaults.retrieval)
        llm = env.get("RESEARCHER_LLM", defaults.llm)
        if retrieval not in ("fixtures", "live"):
            raise ValueError(
                f"RESEARCHER_RETRIEVAL must be 'fixtures' or 'live', got {retrieval!r}"
            )
        if llm not in ("none", "ollama", "llamacpp"):
            raise ValueError(f"RESEARCHER_LLM must be none|ollama|llamacpp, got {llm!r}")
        return cls(
            retrieval=retrieval,  # type: ignore[arg-type]
            llm=llm,  # type: ignore[arg-type]
            fixtures_dir=Path(env.get("RESEARCHER_FIXTURES_DIR", str(defaults.fixtures_dir))),
            db_path=Path(env.get("RESEARCHER_DB", str(defaults.db_path))),
            ollama_host=env.get("RESEARCHER_OLLAMA_HOST", defaults.ollama_host),
            ollama_model=env.get("RESEARCHER_OLLAMA_MODEL", defaults.ollama_model),
            llamacpp_host=env.get("RESEARCHER_LLAMACPP_HOST", defaults.llamacpp_host),
            llm_timeout=float(env.get("RESEARCHER_LLM_TIMEOUT", defaults.llm_timeout)),
            max_workers=int(env.get("RESEARCHER_MAX_WORKERS", defaults.max_workers)),
            simulated_latency=float(env.get("RESEARCHER_SIMULATED_LATENCY", 0.0)),
            allow_private_hosts=env.get("RESEARCHER_ALLOW_PRIVATE_HOSTS", "0") == "1",
            respect_robots=env.get("RESEARCHER_RESPECT_ROBOTS", "1") != "0",
        )
