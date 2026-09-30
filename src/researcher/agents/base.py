"""Agent base class and the per-job context agents read and write."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ..models import AgentLogEntry, Job, LogLevel, TaskKind, TaskRecord
from ..services import Services


class JobContext:
    def __init__(
        self, job: Job, services: Services, on_change: Callable[[Job], None] | None = None
    ) -> None:
        self.job = job
        self.services = services
        self._on_change = on_change

    def log(
        self,
        agent: str,
        event: str,
        message: str,
        *,
        level: LogLevel = "info",
        task_id: str | None = None,
        **data: Any,
    ) -> None:
        self.job.logs.append(
            AgentLogEntry(
                seq=len(self.job.logs) + 1,
                ts=self.services.clock(),
                agent=agent,
                task_id=task_id,
                level=level,
                event=event,
                message=message,
                data=data,
            )
        )
        self.changed()

    def changed(self) -> None:
        self.job.updated_at = self.services.clock()
        if self._on_change:
            self._on_change(self.job)


class Agent(ABC):
    name: str
    kind: TaskKind

    @abstractmethod
    async def run(self, ctx: JobContext, task: TaskRecord) -> None:
        """Do the work for ``task``. Raise TransientError to request a retry."""
