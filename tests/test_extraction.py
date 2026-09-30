import json

import httpx
import pytest

from conftest import ScriptedLLM, make_services, make_source, new_job
from researcher.agents import ExtractionAgent, JobContext, ResearchAgent
from researcher.agents.extraction import heuristic_extract, parse_llm_claims
from researcher.errors import ModelOutputError, PermanentError
from researcher.models import SubQuestion, TaskRecord, content_hash
from researcher.retrieval import HttpFetcher
from researcher.retrieval.html import html_to_text
from researcher.textutil import locate_quote, split_sentences

SQ = SubQuestion(id="sq1", text="What does the Orchard Pump cost?", keywords=["cost", "dollar"])
TEXT = (
    "The pump was installed in 2020. Its total cost was 5 thousand dollars. "
    "Is it reliable? The weather was mild."
)


def test_sentence_offsets_index_back_into_text():
    for span in split_sentences(TEXT):
        assert TEXT[span.start : span.end] == span.text
    assert len(split_sentences(TEXT)) == 4


def test_heuristic_claims_are_verbatim_quotes_from_the_source():
    src = make_source("s1", TEXT)
    claims = heuristic_extract(src, SQ)
    assert [c.text for c in claims] == ["Its total cost was 5 thousand dollars."]
    assert all(c.quote in src.text for c in claims)


def test_source_object_carries_required_fields():
    src = make_source("s1", TEXT)
    assert src.content_hash == content_hash(TEXT) and src.url and src.title
    assert src.retrieved_at and src.source_type == "fixture" and src.claims == []


def test_locate_quote_levels():
    assert locate_quote("total cost was 5", TEXT) == "exact"
    assert locate_quote("TOTAL cost, was 5", TEXT) == "fuzzy"
    assert locate_quote("cost was 9 thousand", TEXT) == "none"
    assert locate_quote("", TEXT) == "none"


def test_llm_claims_with_invented_quotes_are_rejected():
    src = make_source("s1", TEXT)
    raw = json.dumps(
        {
            "claims": [
                {
                    "claim": "The pump cost 5 thousand dollars.",
                    "quote": "Its total cost was 5 thousand dollars.",
                },
                {
                    "claim": "The pump cost 9 million dollars.",
                    "quote": "The pump cost nine million dollars.",
                },
                {"claim": "no quote"},
            ]
        }
    )
    claims, rejected = parse_llm_claims(raw, src, SQ)
    assert len(claims) == 1 and rejected == 2
    assert claims[0].quote in src.text


def test_llm_garbage_raises_model_output_error():
    with pytest.raises(ModelOutputError):
        parse_llm_claims("not json at all", make_source("s1", TEXT), SQ)


async def test_research_and_extraction_agents_populate_job(tmp_path):
    services = make_services(tmp_path)
    job = new_job("What does the Harborview Tidal Pilot cost?", services)
    job.subquestions = [
        SubQuestion(
            id="sq1", text="What does Harborview Tidal Pilot cost?", keywords=["cost", "dollar"]
        )
    ]
    ctx = JobContext(job, services)
    await ResearchAgent().run(
        ctx, TaskRecord(id="r", kind="research", payload={"subquestion_id": "sq1"})
    )
    assert job.sources and all(s.content_hash == content_hash(s.text) for s in job.sources)
    assert all(s.id.startswith("src_") and s.retrieved_at for s in job.sources)
    await ExtractionAgent().run(
        ctx, TaskRecord(id="e", kind="extract", payload={"subquestion_id": "sq1"})
    )
    claims = [c for s in job.sources for c in s.claims]
    assert claims and all(c.quote in s.text for s in job.sources for c in s.claims)
    # duplicate content from another URL is stored once
    await ResearchAgent().run(
        ctx, TaskRecord(id="r2", kind="research", payload={"subquestion_id": "sq1"})
    )
    assert len({s.content_hash for s in job.sources}) == len(job.sources)


async def test_unknown_subquestion_is_a_permanent_error(tmp_path):
    services = make_services(tmp_path)
    ctx = JobContext(new_job("q", services), services)
    with pytest.raises(PermanentError):
        await ResearchAgent().run(
            ctx, TaskRecord(id="r", kind="research", payload={"subquestion_id": "zz"})
        )


async def test_llm_extraction_falls_back_to_rules_on_bad_output(tmp_path):
    services = make_services(tmp_path, ScriptedLLM(lambda _: "sorry"))
    job = new_job("q", services)
    job.subquestions = [SQ]
    src = make_source("s1", TEXT)
    src.subquestion_ids = ["sq1"]
    job.sources = [src]
    await ExtractionAgent().run(
        JobContext(job, services),
        TaskRecord(id="e", kind="extract", payload={"subquestion_id": "sq1"}),
    )
    assert [c.text for c in src.claims] == ["Its total cost was 5 thousand dollars."]
    assert any(e.event == "extract_fallback" for e in job.logs)


def test_html_to_text_drops_scripts_and_navigation():
    title, text = html_to_text(
        "<html><head><title> T </title><script>evil()</script></head>"
        "<body><nav>menu</nav><p>Hello <b>world</b>.</p><footer>f</footer></body></html>"
    )
    assert title == "T" and text == "Hello world."
    assert "evil" not in text and "menu" not in text


def _fetcher(handler, **kw):
    return HttpFetcher(
        user_agent="t",
        max_bytes=1000,
        respect_robots=False,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kw,
    )


async def test_fetcher_blocks_private_hosts_and_bad_schemes():
    f = _fetcher(lambda r: httpx.Response(200, text="x"))
    for url in (
        "http://127.0.0.1/a",
        "http://169.254.169.254/latest",
        "http://10.0.0.5/",
        "file:///etc/passwd",
    ):
        with pytest.raises(PermanentError):
            await f.fetch(url)


async def test_fetcher_extracts_html_and_caps_size():
    body = "<html><title>Hi</title><body><p>" + "a" * 5000 + "</p></body></html>"
    f = _fetcher(
        lambda r: httpx.Response(200, text=body, headers={"content-type": "text/html"}),
        allow_private_hosts=True,
    )
    doc = await f.fetch("http://example.test/page")
    assert doc.title == "Hi" and len(doc.text) <= 1000


async def test_fetcher_honours_robots_txt():
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    f = HttpFetcher(
        user_agent="t",
        max_bytes=1000,
        allow_private_hosts=True,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert (await f.fetch("http://example.test/public")).text == "ok"
    with pytest.raises(PermanentError):
        await f.fetch("http://example.test/private/x")
