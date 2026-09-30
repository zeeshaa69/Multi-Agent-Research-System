import json

from conftest import COST_RISK_Q, FULL_Q, ScriptedLLM, make_services, run_offline
from researcher.models import Job


def _shape(job: Job):
    assert job.report
    return [
        (
            sec.title,
            [(s.kind, s.text, s.claim_ids, s.source_ids, s.confidence) for s in sec.statements],
        )
        for sec in job.report.sections
    ], [s.text for s in job.report.summary]


async def test_offline_workflow_completes_with_all_statement_kinds(tmp_path):
    job = await run_offline(COST_RISK_Q, make_services(tmp_path))
    assert job.status == "completed" and job.report
    kinds = {s.kind for sec in job.report.sections for s in sec.statements} | {
        s.kind for s in job.report.summary
    }
    assert kinds == {"source_supported", "uncertain", "conflicting", "generated_synthesis"}
    assert {t.kind for t in job.tasks} == {
        "plan",
        "research",
        "extract",
        "factcheck",
        "validate_citations",
        "synthesize",
        "write_report",
    }
    assert all(t.status == "done" for t in job.tasks)
    assert {e.agent for e in job.logs} >= {
        "planner",
        "researcher",
        "extractor",
        "fact_checker",
        "citation_validator",
        "synthesizer",
        "report_writer",
    }


async def test_known_conflict_is_reported_as_conflict_not_as_fact(tmp_path):
    job = await run_offline(FULL_Q, make_services(tmp_path))
    assert job.report
    statements = [s for sec in job.report.sections for s in sec.statements]
    capacity = [s for s in statements if "12 megawatts" in s.text]
    assert capacity and all(s.kind == "conflicting" for s in capacity)
    assert all("15 megawatts" in s.text for s in capacity)
    assert not any(s.kind == "source_supported" and "megawatts" in s.text for s in statements)


async def test_hedged_statement_is_uncertain(tmp_path):
    job = await run_offline(COST_RISK_Q, make_services(tmp_path))
    assert job.report
    hedged = [s for sec in job.report.sections for s in sec.statements if "may reduce" in s.text]
    assert hedged and hedged[0].kind == "uncertain"


async def test_report_is_deterministic_across_runs(tmp_path):
    a = await run_offline(FULL_Q, make_services(tmp_path))
    b = await run_offline(FULL_Q, make_services(tmp_path))
    assert _shape(a) == _shape(b)
    assert a.report and b.report and a.report.markdown == b.report.markdown


async def test_question_outside_the_corpus_yields_honest_empty_report(tmp_path):
    job = await run_offline(
        "What is the Zephyr Quantum Bakery and what does it cost?", make_services(tmp_path)
    )
    assert job.status == "completed" and job.report
    assert not job.sources and not job.claims
    assert all(sec.unanswered and not sec.statements for sec in job.report.sections)
    assert [s.kind for s in job.report.summary] == ["generated_synthesis", "generated_synthesis"]
    assert "No usable evidence" in job.report.markdown


async def test_markdown_labels_and_cites_every_statement(tmp_path):
    job = await run_offline(COST_RISK_Q, make_services(tmp_path))
    assert job.report
    md = job.report.markdown
    for label in ("[Source-supported]", "[Uncertain]", "[Conflicting]", "[Generated synthesis]"):
        assert label in md
    assert "## Sources" in md and "## Limitations" in md and "synthetic fixture" in md
    for line in md.splitlines():
        if line.startswith("- **[Source-supported]"):
            assert "[S" in line


async def test_stats_add_up(tmp_path):
    job = await run_offline(COST_RISK_Q, make_services(tmp_path))
    assert job.report
    st = job.report.stats
    assert st["claims_total"] == len(job.claims)
    assert (
        st["claims_supported"]
        + st["claims_uncertain"]
        + st["claims_conflicting"]
        + st["claims_unsupported"]
        == st["claims_total"]
    )
    assert st["sources_retrieved"] == len(job.sources)


async def test_model_overview_is_labelled_synthesis_and_checked(tmp_path):
    def respond(prompt: str) -> str:
        if "Verified statements" in prompt:
            cid = prompt.split("[", 1)[1].split("]", 1)[0]
            return json.dumps(
                {"summary": "The pilot has some evidence on cost and effects.", "claim_ids": [cid]}
            )
        return "unusable"  # planner/extractor fall back to rules

    job = await run_offline(COST_RISK_Q, make_services(tmp_path, ScriptedLLM(respond)))
    assert job.status == "completed" and job.report
    first = job.report.summary[0]
    assert first.kind == "generated_synthesis" and first.claim_ids
    assert "scripted" in " ".join(job.report.limitations)


async def test_model_overview_with_new_numbers_is_rejected(tmp_path):
    def respond(prompt: str) -> str:
        if "Verified statements" in prompt:
            cid = prompt.split("[", 1)[1].split("]", 1)[0]
            return json.dumps({"summary": "The pilot cost 999 dollars.", "claim_ids": [cid]})
        return "unusable"

    job = await run_offline(COST_RISK_Q, make_services(tmp_path, ScriptedLLM(respond)))
    assert job.report
    assert not any("999" in s.text for s in job.report.summary)
    assert any(e.event == "summary_fallback" for e in job.logs)
