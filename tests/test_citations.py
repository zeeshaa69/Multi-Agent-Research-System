from datetime import UTC, datetime

from conftest import COST_RISK_Q, make_services, make_source, run_offline
from researcher.agents.citations import validate_claims, validate_report
from researcher.models import Claim, Report, ReportStatement, SourceRef


def claim_with(source_id: str, quote: str, status="supported") -> Claim:
    return Claim(
        id="cl1",
        claim="x",
        verification_status=status,
        confidence=0.5,
        supporting_sources=[SourceRef(source_id=source_id, quote=quote, claim_id="c1")],
    )


def test_valid_citation_passes():
    s = make_source("s1", "The wall is long.")
    c = claim_with("s1", "The wall is long.")
    assert validate_claims([c], [s]) == [] and c.verification_status == "supported"


def test_citation_to_missing_source_demotes_claim():
    c = claim_with("ghost", "The wall is long.")
    issues = validate_claims([c], [make_source("s1", "The wall is long.")])
    assert issues[0].problem == "source does not exist"
    assert c.verification_status == "unsupported" and not c.supporting_sources


def test_quote_missing_from_source_is_dropped():
    c = claim_with("s1", "The wall is short.")
    issues = validate_claims([c], [make_source("s1", "The wall is long.")])
    assert issues[0].problem == "quote not found in source text"
    assert c.verification_status == "unsupported"


def test_tampered_source_text_is_detected():
    s = make_source("s1", "The wall is long.")
    s.text = "The wall is long. Injected text."
    c = claim_with("s1", "The wall is long.")
    assert "content hash" in validate_claims([c], [s])[0].problem


def _report(*statements: ReportStatement) -> Report:
    return Report(
        job_id="j", question="q", generated_at=datetime.now(UTC), summary=list(statements)
    )


def test_report_validation_flags_uncited_and_mismatched_statements():
    s = make_source("s1", "The wall is long.")
    good = claim_with("s1", "The wall is long.")
    ok = ReportStatement(
        id="a", text="x", kind="source_supported", claim_ids=["cl1"], source_ids=["s1"]
    )
    assert validate_report(_report(ok), [good], [s]) == []
    bad = [
        ReportStatement(id="b", text="x", kind="source_supported"),
        ReportStatement(
            id="c", text="x", kind="source_supported", claim_ids=["nope"], source_ids=["s1"]
        ),
        ReportStatement(
            id="d", text="x", kind="source_supported", claim_ids=["cl1"], source_ids=["zzz"]
        ),
        ReportStatement(id="e", text="x", kind="conflicting", claim_ids=["cl1"], source_ids=["s1"]),
    ]
    problems = validate_report(_report(*bad), [good], [s])
    assert len(problems) >= 5
    assert any("unknown claim" in p for p in problems) and any(
        "unknown source" in p for p in problems
    )
    assert any("is conflicting but claim" in p for p in problems)


def test_generated_synthesis_may_have_no_citations():
    st = ReportStatement(id="g", text="Overview", kind="generated_synthesis")
    assert validate_report(_report(st), [], []) == []


async def test_every_sourced_statement_maps_to_real_sources_and_quotes(tmp_path):
    job = await run_offline(COST_RISK_Q, make_services(tmp_path))
    assert job.report is not None
    statements = [s for sec in job.report.sections for s in sec.statements]
    assert statements
    for st in statements:
        assert st.claim_ids and st.source_ids
        for cid in st.claim_ids:
            claim = job.claim_by_id(cid)
            assert claim is not None
            for ref in claim.supporting_sources:
                src = job.source_by_id(ref.source_id)
                assert src is not None and ref.quote in src.text
    assert set(job.report.source_ids) <= {s.id for s in job.sources}
    assert validate_report(job.report, job.claims, job.sources) == []
