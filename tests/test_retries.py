import httpx
import pytest

from conftest import FULL_Q, make_services, new_job
from researcher.agents import ResearchAgent
from researcher.config import RetryConfig
from researcher.errors import PermanentError, TransientError
from researcher.llm import OllamaClient
from researcher.orchestration import default_router, run_job
from researcher.orchestration.router import AgentRouter
from researcher.retry import backoff_delay, with_retry


def test_backoff_grows_and_is_capped():
    cfg = RetryConfig(base_delay=1.0, factor=2.0, max_delay=5.0)
    assert [backoff_delay(cfg, n) for n in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 5.0]


async def test_with_retry_succeeds_after_transient_failures():
    calls, delays = 0, []

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientError("try again")
        return "ok"

    async def sleep(d: float) -> None:
        delays.append(d)

    result, attempts = await with_retry(
        flaky, RetryConfig(max_attempts=3, base_delay=1), sleep=sleep
    )
    assert (result, attempts, delays) == ("ok", 3, [1.0, 2.0])


async def test_with_retry_gives_up_and_does_not_retry_permanent_errors():
    async def always() -> None:
        raise TransientError("down")

    async def perm() -> None:
        raise PermanentError("bad")

    async def sleep(_: float) -> None: ...

    with pytest.raises(TransientError):
        await with_retry(always, RetryConfig(max_attempts=2), sleep=sleep)
    calls = 0

    async def counted() -> None:
        nonlocal calls
        calls += 1
        await perm()

    with pytest.raises(PermanentError):
        await with_retry(counted, RetryConfig(max_attempts=5), sleep=sleep)
    assert calls == 1


class FlakyRetriever:
    """Wraps the fixture retriever; the first ``failures`` searches raise a transient error."""

    name = "flaky"

    def __init__(self, inner, failures: int) -> None:
        self.inner, self.failures, self.searches = inner, failures, 0

    async def search(self, query, limit):
        self.searches += 1
        if self.failures > 0:
            self.failures -= 1
            raise TransientError("search backend unavailable")
        return await self.inner.search(query, limit)

    async def fetch(self, hit):
        return await self.inner.fetch(hit)

    async def fetch_url(self, url):
        return await self.inner.fetch_url(url)


async def test_pipeline_retries_transient_research_failures(tmp_path):
    services = make_services(tmp_path)
    services.retriever = FlakyRetriever(services.retriever, failures=2)
    job = await run_job(new_job(FULL_Q, services), services)
    assert job.status == "completed"
    retried = [t for t in job.tasks if t.attempts > 1]
    assert retried, "at least one task should record more than one attempt"
    assert sum(1 for e in job.logs if e.event == "retry") >= 2


async def test_exhausted_retries_degrade_gracefully_without_fabrication(tmp_path):
    services = make_services(tmp_path)
    services.retriever = FlakyRetriever(services.retriever, failures=10**6)
    job = await run_job(new_job(FULL_Q, services), services)
    failed = [t for t in job.tasks if t.kind == "research"]
    assert failed and all(t.status == "failed" and t.attempts == 3 for t in failed)
    assert job.status == "completed"  # a report is still produced, honestly empty
    assert job.report is not None and not job.sources and not job.claims
    assert all(sec.unanswered for sec in job.report.sections)
    assert job.report.stats["statements_source_supported"] == 0
    assert any("research-sq1" in w for w in job.warnings)


async def test_permanent_error_is_not_retried(tmp_path):
    services = make_services(tmp_path)

    class Broken(ResearchAgent):
        async def run(self, ctx, task):
            raise PermanentError("nope")

    agents = [a for a in default_router()._by_kind.values() if a.kind != "research"] + [Broken()]
    job = await run_job(new_job(FULL_Q, services), services, router=AgentRouter(agents))
    research = [t for t in job.tasks if t.kind == "research"]
    assert all(t.status == "failed" and t.attempts <= 1 for t in research)
    assert not any(e.event == "retry" for e in job.logs)


async def test_ollama_client_maps_http_errors_to_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = OllamaClient(
        "http://x", "m", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(TransientError):
        await client.complete("hi")


async def test_ollama_client_returns_response_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"response": "hello"})

    client = OllamaClient(
        "http://x", "m", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await client.complete("hi", system="s") == "hello"
    assert b'"stream":false' in seen["body"].replace(b" ", b"")
