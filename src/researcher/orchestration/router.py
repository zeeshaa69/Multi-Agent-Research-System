"""Routes task kinds to the agent responsible for them."""

from __future__ import annotations

from ..agents import (
    Agent,
    CitationValidatorAgent,
    ExtractionAgent,
    FactCheckerAgent,
    PlannerAgent,
    ReportWriterAgent,
    ResearchAgent,
    SynthesisAgent,
)
from ..errors import RoutingError
from ..models import TaskKind


class AgentRouter:
    def __init__(self, agents: list[Agent]) -> None:
        self._by_kind: dict[TaskKind, Agent] = {}
        for agent in agents:
            if agent.kind in self._by_kind:
                raise ValueError(f"two agents registered for {agent.kind}")
            self._by_kind[agent.kind] = agent

    def route(self, kind: TaskKind) -> Agent:
        try:
            return self._by_kind[kind]
        except KeyError:
            raise RoutingError(f"no agent registered for task kind {kind!r}") from None


def default_router() -> AgentRouter:
    return AgentRouter(
        [
            PlannerAgent(),
            ResearchAgent(),
            ExtractionAgent(),
            FactCheckerAgent(),
            CitationValidatorAgent(),
            SynthesisAgent(),
            ReportWriterAgent(),
        ]
    )
