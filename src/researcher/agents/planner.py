"""Planner Agent: break a question into sub-questions."""

from __future__ import annotations

import re

from ..errors import ModelOutputError, PermanentError
from ..llm import parse_json_response
from ..models import SubQuestion, TaskRecord
from ..textutil import STOPWORDS
from .base import Agent, JobContext

# (trigger substrings in the lower-cased question, sub-question template, relevance keywords)
ASPECTS: list[tuple[tuple[str, ...], str, list[str]]] = [
    (
        ("cost", "price", "expens", "fund", "budget", "afford"),
        "What does {t} cost?",
        ["cost", "price", "dollar", "budget", "fund", "expense", "spend"],
    ),
    (
        (
            "produce",
            "output",
            "capacity",
            "power",
            "performance",
            "generat",
            "efficien",
            "how much",
        ),
        "What is the capacity and output of {t}?",
        ["capacity", "output", "power", "electricity", "megawatt", "gigawatt", "generate"],
    ),
    (
        ("environment", "impact", "effect", "ecolog", "wildlife", "emission"),
        "What are the environmental effects of {t}?",
        ["environment", "impact", "monitor", "wildlife", "fish", "emission", "noise"],
    ),
    (
        ("risk", "limit", "critic", "problem", "challenge", "drawback", "downside"),
        "What are the risks or limitations of {t}?",
        ["risk", "limit", "problem", "challenge", "concern", "criticism", "require"],
    ),
    (
        ("who ", "develop", "built", "build", "company", "organi", "operator"),
        "Who developed or operates {t}?",
        ["developed", "operator", "company", "consortium", "owner", "built"],
    ),
    (
        ("when", "history", "began", "timeline", "start"),
        "When did {t} begin and what is its timeline?",
        ["began", "started", "year", "operation", "construction", "completed"],
    ),
]
DEFINITION_KEYWORDS = ["project", "located", "developed", "began", "uses", "construction"]
FALLBACK = (
    "What are the risks or limitations of {t}?",
    ["risk", "limit", "problem", "challenge", "concern", "require"],
)


def extract_topic(question: str) -> str:
    """Longest run of capitalised non-stopword words; else the leading content words."""
    tokens = re.findall(r"[A-Za-z0-9'-]+", question)
    best: list[str] = []
    run: list[str] = []
    for tok in tokens:
        if tok[0].isupper() and tok.lower() not in STOPWORDS:
            run.append(tok)
            if len(run) > len(best):
                best = list(run)
        else:
            run = []
    if best:
        return " ".join(best)
    content = [t for t in tokens if t.lower() not in STOPWORDS]
    return " ".join(content[:6]) or question.strip()


def heuristic_plan(question: str, max_subquestions: int) -> list[SubQuestion]:
    topic = extract_topic(question)
    lowered = question.lower()
    specs: list[tuple[str, list[str], str]] = [
        (f"What is {topic}?", DEFINITION_KEYWORDS, "Establish what the subject is.")
    ]
    for triggers, template, keywords in ASPECTS:
        hit = next((t for t in triggers if t in lowered), None)
        if hit:
            specs.append(
                (template.format(t=topic), keywords, f"Question mentions '{hit.strip()}'.")
            )
    if len(specs) == 1:
        text, kws = FALLBACK
        specs.append((text.format(t=topic), kws, "Default: look for caveats."))
    return [
        SubQuestion(id=f"sq{i}", text=text, keywords=kws, rationale=why)
        for i, (text, kws, why) in enumerate(specs[:max_subquestions], start=1)
    ]


def _parse_llm_plan(raw: str, limit: int) -> list[SubQuestion]:
    data = parse_json_response(raw)
    items = data.get("subquestions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ModelOutputError("plan JSON has no 'subquestions' list")
    out: list[SubQuestion] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            text, kws = item, []
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            text = item["text"]
            kws = [k for k in item.get("keywords", []) if isinstance(k, str)]
        else:
            continue
        text = " ".join(text.split())[:200]
        if len(text) < 8 or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(SubQuestion(id=f"sq{len(out) + 1}", text=text, keywords=kws[:10]))
        if len(out) == limit:
            break
    if not out:
        raise ModelOutputError("plan contained no usable sub-questions")
    return out


class PlannerAgent(Agent):
    name = "planner"
    kind = "plan"

    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        job = ctx.job
        limit = job.options.max_subquestions
        llm = ctx.services.llm
        plan: list[SubQuestion] | None = None
        if llm is not None:
            prompt = (
                "Break the research question into at most "
                f"{limit} specific sub-questions that can each be answered from documents.\n"
                'Reply with JSON only: {"subquestions": [{"text": "...", "keywords": ["..."]}]}\n'
                f"Question: {job.question}"
            )
            raw = await llm.complete(prompt, system="You are a careful research planner.")
            try:
                plan = _parse_llm_plan(raw, limit)
                ctx.log(
                    self.name,
                    "plan_llm",
                    f"model {llm.name} produced {len(plan)} sub-questions",
                    task_id=task.id,
                )
            except ModelOutputError as exc:
                ctx.log(
                    self.name,
                    "plan_fallback",
                    f"model output rejected ({exc}); using rules",
                    level="warning",
                    task_id=task.id,
                )
        if plan is None:
            plan = heuristic_plan(job.question, limit)
            ctx.log(
                self.name,
                "plan_rules",
                f"rule-based plan with {len(plan)} sub-questions",
                task_id=task.id,
            )
        if not plan:
            raise PermanentError("planner produced no sub-questions")
        job.subquestions = plan
        ctx.changed()
