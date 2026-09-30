"""HTTP API (FastAPI). Binds to localhost by default; there is no authentication."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings
from .models import AgentLogEntry, Claim, Job, JobOptions, JobSummary, Report, Source
from .orchestration import AgentRouter, JobManager
from .services import Services, build_services
from .storage import Store, summarize


class CreateJobRequest(BaseModel):
    question: str = Field(min_length=8, max_length=1000)
    options: JobOptions = Field(default_factory=JobOptions)


def create_app(
    settings: Settings | None = None,
    services: Services | None = None,
    router: AgentRouter | None = None,
) -> FastAPI:
    cfg = settings or (services.settings if services else Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(cfg.db_path)
        manager = JobManager(services or build_services(cfg), store, router)
        app.state.manager = manager
        yield
        await manager.shutdown()
        store.close()

    app = FastAPI(title="Multi-Agent Researcher", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    def manager() -> JobManager:
        m: JobManager = app.state.manager
        return m

    def job_or_404(job_id: str) -> Job:
        job = manager().get(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "mode": cfg.mode,
            "retrieval": cfg.retrieval,
            "llm": cfg.llm,
            "model": cfg.ollama_model if cfg.llm == "ollama" else None,
        }

    @app.post("/api/jobs", status_code=202)
    async def create_job(req: CreateJobRequest) -> JobSummary:
        return summarize(manager().submit(req.question, req.options))

    @app.get("/api/jobs")
    async def list_jobs() -> list[JobSummary]:
        return [summarize(j) for j in manager().list()]

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> Job:
        return job_or_404(job_id)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: str) -> None:
        job_or_404(job_id)
        if not manager().delete(job_id):
            raise HTTPException(409, "job is still running")

    @app.get("/api/jobs/{job_id}/sources")
    async def get_sources(job_id: str) -> list[Source]:
        return job_or_404(job_id).sources

    @app.get("/api/jobs/{job_id}/claims")
    async def get_claims(job_id: str) -> list[Claim]:
        return job_or_404(job_id).claims

    @app.get("/api/jobs/{job_id}/logs")
    async def get_logs(job_id: str, after: int = 0) -> list[AgentLogEntry]:
        return [e for e in job_or_404(job_id).logs if e.seq > after]

    @app.get("/api/jobs/{job_id}/report")
    async def get_report(job_id: str) -> Report:
        report = job_or_404(job_id).report
        if report is None:
            raise HTTPException(404, "report not available yet")
        return report

    @app.get("/api/jobs/{job_id}/report.md", response_class=PlainTextResponse)
    async def get_report_markdown(job_id: str) -> str:
        report = job_or_404(job_id).report
        if report is None:
            raise HTTPException(404, "report not available yet")
        return report.markdown

    dist = cfg.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def app_factory() -> FastAPI:
    return create_app()
