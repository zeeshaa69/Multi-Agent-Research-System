"""Dependency-aware task queue with a bounded worker pool, retries and timeouts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from ..agents import JobContext
from ..config import RetryConfig
from ..errors import PermanentError, ResearchError, TransientError
from ..models import TaskRecord
from ..retry import Sleep, with_retry
from .router import AgentRouter


class TaskQueue:
    def __init__(
        self,
        ctx: JobContext,
        router: AgentRouter,
        *,
        max_workers: int,
        retry: RetryConfig,
        task_timeout: float,
        sleep: Sleep = asyncio.sleep,
        on_done: Callable[[TaskRecord], list[TaskRecord]] | None = None,
    ) -> None:
        self._ctx = ctx
        self._router = router
        self._max_workers = max_workers
        self._retry = retry
        self._timeout = task_timeout
        self._sleep = sleep
        self._on_done = on_done
        self._tasks: dict[str, TaskRecord] = {t.id: t for t in ctx.job.tasks}

    def add(self, task: TaskRecord) -> None:
        if task.id in self._tasks:
            raise ValueError(f"duplicate task id {task.id}")
        self._tasks[task.id] = task
        self._ctx.job.tasks.append(task)
        self._ctx.changed()

    def _ready(self, task: TaskRecord) -> bool:
        deps = [self._tasks[d] for d in task.deps]
        if any(d.status in ("pending", "running") for d in deps):
            return False
        return task.allow_failed_deps or all(d.status == "done" for d in deps)

    def _skip_blocked(self) -> None:
        for t in self._tasks.values():
            if t.status != "pending" or t.allow_failed_deps:
                continue
            bad = [d for d in t.deps if self._tasks[d].status in ("failed", "skipped")]
            if bad:
                t.status = "skipped"
                t.error = f"dependency {bad[0]} did not complete"
                t.finished_at = self._ctx.services.clock()
                self._ctx.log(
                    "orchestrator",
                    "task_skipped",
                    f"{t.id} skipped: {t.error}",
                    level="warning",
                    task_id=t.id,
                )
                self._ctx.changed()

    async def run(self) -> None:
        running: set[asyncio.Task[None]] = set()
        while True:
            self._skip_blocked()
            for t in list(self._tasks.values()):
                if len(running) >= self._max_workers:
                    break
                if t.status == "pending" and self._ready(t):
                    t.status = "running"
                    running.add(asyncio.create_task(self._execute(t)))
            if not running:
                for t in self._tasks.values():
                    if t.status == "pending":  # unreachable deps: should not happen
                        t.status = "skipped"
                        t.error = "unsatisfiable dependencies"
                break
            done, running = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for fut in done:
                fut.result()
        self._ctx.changed()

    async def _execute(self, task: TaskRecord) -> None:
        ctx = self._ctx
        task.started_at = ctx.services.clock()
        try:
            agent = self._router.route(task.kind)
            task.agent = agent.name
            ctx.log(agent.name, "task_started", f"{task.id} started", task_id=task.id)

            def note_retry(attempt: int, exc: Exception, delay: float) -> None:
                task.attempts = attempt
                ctx.log(
                    agent.name,
                    "retry",
                    f"{task.id} attempt {attempt} failed ({exc}); retrying in {delay:.1f}s",
                    level="warning",
                    task_id=task.id,
                )

            async def attempt() -> None:
                await asyncio.wait_for(agent.run(ctx, task), timeout=self._timeout)

            try:
                _, attempts = await with_retry(
                    attempt, self._retry, sleep=self._sleep, on_retry=note_retry
                )
            except TimeoutError as exc:
                raise PermanentError(f"timed out after {self._timeout:.0f}s") from exc
            task.attempts = attempts
            task.status = "done"
            ctx.log(
                agent.name,
                "task_done",
                f"{task.id} finished after {attempts} attempt(s)",
                task_id=task.id,
            )
        except (TransientError, ResearchError) as exc:
            if isinstance(exc, TransientError):
                task.attempts = self._retry.max_attempts
            task.status = "failed"
            task.error = str(exc)
            ctx.log(
                task.agent or "orchestrator",
                "task_failed",
                f"{task.id} failed: {exc}",
                level="error",
                task_id=task.id,
            )
        except Exception as exc:
            task.status = "failed"
            task.error = f"{type(exc).__name__}: {exc}"
            ctx.log(
                task.agent or "orchestrator",
                "task_crashed",
                f"{task.id} crashed: {task.error}",
                level="error",
                task_id=task.id,
            )
        task.finished_at = ctx.services.clock()
        ctx.changed()
        if task.status == "done" and self._on_done:
            for new_task in self._on_done(task):
                self.add(new_task)
