"""Creates jobs, runs them in the background, and persists history."""

from __future__ import annotations

import asyncio
import uuid

from ..models import Job, JobOptions
from ..services import Services
from ..storage import Store
from .pipeline import run_job
from .router import AgentRouter


class JobManager:
    def __init__(self, services: Services, store: Store, router: AgentRouter | None = None) -> None:
        self._services = services
        self._store = store
        self._router = router
        self._running: dict[str, asyncio.Task[Job]] = {}
        self._slots = asyncio.Semaphore(services.settings.max_concurrent_jobs)
        self._live: dict[str, Job] = {}
        for job in store.list():
            if job.status in ("queued", "running"):
                job.status = "failed"
                job.error = "interrupted: the server stopped before this job finished"
                store.save(job)

    def submit(self, question: str, options: JobOptions | None = None) -> Job:
        now = self._services.clock()
        job = Job(
            id=uuid.uuid4().hex[:12],
            question=question.strip(),
            mode=self._services.settings.mode,
            created_at=now,
            updated_at=now,
            options=options or JobOptions(),
        )
        self._live[job.id] = job
        self._store.save(job)
        self._running[job.id] = asyncio.create_task(self._run(job))
        return job

    async def _run(self, job: Job) -> Job:
        try:
            async with self._slots:
                return await run_job(
                    job, self._services, router=self._router, on_change=self._store.save
                )
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            return job
        finally:
            self._store.save(job)
            self._live.pop(job.id, None)

    def get(self, job_id: str) -> Job | None:
        return self._live.get(job_id) or self._store.get(job_id)

    def list(self) -> list[Job]:
        live = self._live
        stored = [live.get(j.id, j) for j in self._store.list()]
        return stored

    def delete(self, job_id: str) -> bool:
        if job_id in self._live:
            return False
        return self._store.delete(job_id)

    async def wait(self, job_id: str) -> Job:
        task = self._running.get(job_id)
        if task is not None:
            await task
        job = self.get(job_id)
        assert job is not None
        return job

    async def shutdown(self) -> None:
        for task in self._running.values():
            task.cancel()
        await asyncio.gather(*self._running.values(), return_exceptions=True)
