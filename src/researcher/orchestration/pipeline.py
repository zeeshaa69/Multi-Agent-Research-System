"""Builds the research task graph and runs one job to completion."""

from __future__ import annotations

from collections.abc import Callable

from ..agents import JobContext
from ..models import Job, TaskRecord
from ..services import Services
from .queue import TaskQueue
from .router import AgentRouter, default_router


def expand_after_plan(job: Job) -> list[TaskRecord]:
    """Fan out one research + extraction task per sub-question, then the aggregate chain."""
    tasks: list[TaskRecord] = []
    extract_ids: list[str] = []
    for sq in job.subquestions:
        research = TaskRecord(
            id=f"research-{sq.id}",
            kind="research",
            payload={"subquestion_id": sq.id},
            deps=["plan"],
        )
        extract = TaskRecord(
            id=f"extract-{sq.id}",
            kind="extract",
            payload={"subquestion_id": sq.id},
            deps=[research.id],
        )
        extract_ids.append(extract.id)
        tasks += [research, extract]
    tasks += [
        TaskRecord(id="factcheck", kind="factcheck", deps=extract_ids, allow_failed_deps=True),
        TaskRecord(id="validate_citations", kind="validate_citations", deps=["factcheck"]),
        TaskRecord(id="synthesize", kind="synthesize", deps=["validate_citations"]),
        TaskRecord(id="write_report", kind="write_report", deps=["synthesize"]),
    ]
    return tasks


async def run_job(
    job: Job,
    services: Services,
    *,
    router: AgentRouter | None = None,
    on_change: Callable[[Job], None] | None = None,
) -> Job:
    ctx = JobContext(job, services, on_change)
    cfg = services.settings

    def on_done(task: TaskRecord) -> list[TaskRecord]:
        return expand_after_plan(job) if task.kind == "plan" else []

    queue = TaskQueue(
        ctx,
        router or default_router(),
        max_workers=cfg.max_workers,
        retry=cfg.retry,
        task_timeout=cfg.task_timeout,
        sleep=services.sleep,
        on_done=on_done,
    )
    job.status = "running"
    ctx.log("orchestrator", "job_started", f"job started in {job.mode} mode")
    queue.add(TaskRecord(id="plan", kind="plan"))
    await queue.run()

    by_id = {t.id: t for t in job.tasks}
    for t in job.tasks:
        if t.kind in ("research", "extract") and t.status != "done":
            job.warnings.append(
                f"task {t.id} {t.status}: {t.error or 'not run'}; "
                "its sub-question may have incomplete evidence."
            )
    final = by_id.get("write_report")
    if final is not None and final.status == "done" and job.report is not None:
        job.status = "completed"
        ctx.log("orchestrator", "job_completed", "job completed")
    else:
        failed = next((t for t in job.tasks if t.status == "failed"), None)
        job.status = "failed"
        job.error = f"{failed.id}: {failed.error}" if failed else "pipeline did not finish"
        ctx.log("orchestrator", "job_failed", job.error, level="error")
    ctx.changed()
    return job
