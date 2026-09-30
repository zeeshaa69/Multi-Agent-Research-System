import asyncio

import pytest

from conftest import make_services, new_job
from researcher.agents import Agent, JobContext
from researcher.config import RetryConfig
from researcher.errors import RoutingError
from researcher.models import SubQuestion, TaskKind, TaskRecord
from researcher.orchestration import AgentRouter, TaskQueue, default_router, expand_after_plan

ALL_KINDS: list[TaskKind] = [
    "plan",
    "research",
    "extract",
    "factcheck",
    "validate_citations",
    "synthesize",
    "write_report",
]


def test_every_task_kind_routes_to_its_own_agent():
    router = default_router()
    names = {router.route(k).name for k in ALL_KINDS}
    assert len(names) == 7
    assert router.route("plan").name == "planner"
    assert router.route("factcheck").name == "fact_checker"


def test_unknown_kind_raises_routing_error():
    with pytest.raises(RoutingError):
        AgentRouter([]).route("plan")


class Recorder(Agent):
    def __init__(self, kind: TaskKind, log: list[str], delay: float = 0.0, fail: bool = False):
        self.kind, self.name, self.log, self.delay, self.fail = (
            kind,
            f"rec-{kind}",
            log,
            delay,
            fail,
        )
        self.active = 0
        self.peak = 0

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        if self.fail:
            from researcher.errors import PermanentError

            raise PermanentError("boom")
        self.log.append(task.id)


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError):
        AgentRouter([Recorder("plan", []), Recorder("plan", [])])


def _queue(tmp_path, agents, workers=4, **kw):
    services = make_services(tmp_path)
    job = new_job("q", services)
    ctx = JobContext(job, services)
    return job, TaskQueue(
        ctx,
        AgentRouter(agents),
        max_workers=workers,
        retry=RetryConfig(base_delay=0),
        task_timeout=5,
        sleep=services.sleep,
        **kw,
    )


async def test_dependencies_respected_and_parallelism_bounded(tmp_path):
    log: list[str] = []
    research = Recorder("research", log, delay=0.02)
    agents = [Recorder("plan", log), research, Recorder("extract", log), Recorder("factcheck", log)]
    job, q = _queue(tmp_path, agents, workers=2)
    q.add(TaskRecord(id="plan", kind="plan"))
    for i in range(4):
        q.add(TaskRecord(id=f"r{i}", kind="research", deps=["plan"]))
    q.add(TaskRecord(id="fc", kind="factcheck", deps=[f"r{i}" for i in range(4)]))
    await q.run()
    assert log[0] == "plan" and log[-1] == "fc"
    assert research.peak == 2  # ran in parallel, but never above max_workers
    assert all(t.status == "done" for t in job.tasks)
    assert {t.agent for t in job.tasks} == {"rec-plan", "rec-research", "rec-factcheck"}


async def test_failed_dependency_skips_dependents_unless_allowed(tmp_path):
    log: list[str] = []
    agents = [
        Recorder("research", log, fail=True),
        Recorder("extract", log),
        Recorder("factcheck", log),
    ]
    job, q = _queue(tmp_path, agents)
    q.add(TaskRecord(id="r", kind="research"))
    q.add(TaskRecord(id="e", kind="extract", deps=["r"]))
    q.add(TaskRecord(id="f", kind="factcheck", deps=["e"], allow_failed_deps=True))
    await q.run()
    status = {t.id: t.status for t in job.tasks}
    assert status == {"r": "failed", "e": "skipped", "f": "done"}


def test_plan_fans_out_research_and_extract_per_subquestion(tmp_path):
    job = new_job("q", make_services(tmp_path))
    job.subquestions = [SubQuestion(id="sq1", text="a"), SubQuestion(id="sq2", text="b")]
    tasks = {t.id: t for t in expand_after_plan(job)}
    assert tasks["research-sq2"].deps == ["plan"]
    assert tasks["extract-sq2"].deps == ["research-sq2"]
    assert set(tasks["factcheck"].deps) == {"extract-sq1", "extract-sq2"}
    assert tasks["factcheck"].allow_failed_deps
    assert tasks["write_report"].deps == ["synthesize"]
