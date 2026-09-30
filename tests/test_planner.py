import json

from conftest import FULL_Q, ScriptedLLM, make_services, new_job
from researcher.agents import JobContext, PlannerAgent
from researcher.agents.planner import extract_topic, heuristic_plan
from researcher.models import TaskRecord


def test_topic_is_longest_capitalised_run():
    assert extract_topic(FULL_Q) == "Harborview Tidal Pilot"


def test_topic_falls_back_to_content_words():
    assert extract_topic("how do tidal turbines work") == "tidal turbines work"


def test_plan_covers_aspects_named_in_question():
    plan = heuristic_plan(FULL_Q, 5)
    texts = [q.text for q in plan]
    assert texts[0] == "What is Harborview Tidal Pilot?"
    assert any("cost" in t for t in texts)
    assert any("capacity and output" in t for t in texts)
    assert [q.id for q in plan] == ["sq1", "sq2", "sq3"]
    assert all(q.keywords for q in plan)


def test_plan_respects_limit_and_is_deterministic():
    q = "What are the costs, risks, environmental effects and history of the Harborview Pilot?"
    assert len(heuristic_plan(q, 2)) == 2
    assert heuristic_plan(q, 5) == heuristic_plan(q, 5)


def test_plan_default_when_no_aspect_matches():
    plan = heuristic_plan("Tell me about the Harborview Pilot", 5)
    assert len(plan) == 2
    assert "risks" in plan[1].text


async def _plan_with(tmp_path, response: str):
    llm = ScriptedLLM(lambda _: response)
    services = make_services(tmp_path, llm)
    job = new_job(FULL_Q, services)
    ctx = JobContext(job, services)
    await PlannerAgent().run(ctx, TaskRecord(id="plan", kind="plan"))
    return job


async def test_llm_plan_is_used_when_valid(tmp_path):
    raw = json.dumps(
        {
            "subquestions": [
                {"text": "What is the capacity of the pilot?", "keywords": ["capacity"]},
                "What did the pilot cost to build?",
            ]
        }
    )
    job = await _plan_with(tmp_path, "```json\n" + raw + "\n```")
    assert [q.text for q in job.subquestions] == [
        "What is the capacity of the pilot?",
        "What did the pilot cost to build?",
    ]
    assert any(e.event == "plan_llm" for e in job.logs)


async def test_invalid_llm_plan_falls_back_to_rules(tmp_path):
    job = await _plan_with(tmp_path, "I cannot do that")
    assert job.subquestions == heuristic_plan(FULL_Q, 5)
    assert any(e.event == "plan_fallback" and e.level == "warning" for e in job.logs)
