"""Data model shared by agents, storage and the HTTP API."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal["web", "encyclopedia", "paper", "user_supplied", "fixture"]
VerificationStatus = Literal["supported", "uncertain", "conflicting", "unsupported"]
StatementKind = Literal["source_supported", "uncertain", "conflicting", "generated_synthesis"]
TaskKind = Literal[
    "plan", "research", "extract", "factcheck", "validate_citations", "synthesize", "write_report"
]
TaskStatus = Literal["pending", "running", "done", "failed", "skipped"]
JobStatus = Literal["queued", "running", "completed", "failed"]
Grounding = Literal["unchecked", "exact", "fuzzy", "none"]
LogLevel = Literal["info", "warning", "error"]


def utcnow() -> datetime:
    return datetime.now(UTC)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


class SubQuestion(BaseModel):
    id: str
    text: str
    keywords: list[str] = Field(default_factory=list)
    rationale: str = ""


class ExtractedClaim(BaseModel):
    """A statement pulled out of one source together with its verbatim evidence quote."""

    id: str
    text: str
    quote: str
    relevance: dict[str, float] = Field(default_factory=dict)
    hedged: bool = False
    grounding: Grounding = "unchecked"


class Source(BaseModel):
    id: str
    url: str
    title: str
    retrieved_at: datetime
    text: str
    source_type: SourceType
    content_hash: str
    claims: list[ExtractedClaim] = Field(default_factory=list)
    subquestion_ids: list[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    source_id: str
    quote: str
    claim_id: str


class ConflictEvidence(BaseModel):
    source_id: str
    claim_id: str
    statement: str
    quote: str
    reason: str


class Claim(BaseModel):
    id: str
    claim: str
    supporting_sources: list[SourceRef] = Field(default_factory=list)
    confidence: float = 0.0
    verification_status: VerificationStatus = "unsupported"
    conflicting_evidence: list[ConflictEvidence] = Field(default_factory=list)
    subquestion_ids: list[str] = Field(default_factory=list)
    hedged: bool = False
    notes: list[str] = Field(default_factory=list)


class CitationIssue(BaseModel):
    claim_id: str
    source_id: str | None = None
    problem: str


class ReportStatement(BaseModel):
    id: str
    text: str
    kind: StatementKind
    claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None


class ReportSection(BaseModel):
    subquestion_id: str
    title: str
    statements: list[ReportStatement] = Field(default_factory=list)
    unanswered: bool = False


class Report(BaseModel):
    job_id: str
    question: str
    generated_at: datetime
    summary: list[ReportStatement] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    excluded_claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    markdown: str = ""


class TaskRecord(BaseModel):
    id: str
    kind: TaskKind
    agent: str = ""
    deps: list[str] = Field(default_factory=list)
    allow_failed_deps: bool = False
    status: TaskStatus = "pending"
    attempts: int = 0
    error: str | None = None
    payload: dict[str, str] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentLogEntry(BaseModel):
    seq: int
    ts: datetime
    agent: str
    task_id: str | None = None
    level: LogLevel = "info"
    event: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class JobOptions(BaseModel):
    max_subquestions: int = Field(default=5, ge=1, le=8)
    sources_per_subquestion: int = Field(default=5, ge=1, le=10)
    seed_urls: list[str] = Field(default_factory=list, max_length=10)


class Job(BaseModel):
    id: str
    question: str
    status: JobStatus = "queued"
    mode: str = "offline"
    created_at: datetime
    updated_at: datetime
    options: JobOptions = Field(default_factory=JobOptions)
    subquestions: list[SubQuestion] = Field(default_factory=list)
    tasks: list[TaskRecord] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    citation_issues: list[CitationIssue] = Field(default_factory=list)
    draft: Report | None = None
    report: Report | None = None
    logs: list[AgentLogEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

    def source_by_id(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def claim_by_id(self, claim_id: str) -> Claim | None:
        return next((c for c in self.claims if c.id == claim_id), None)

    def subquestion_by_id(self, sq_id: str) -> SubQuestion | None:
        return next((q for q in self.subquestions if q.id == sq_id), None)


class JobSummary(BaseModel):
    id: str
    question: str
    status: JobStatus
    mode: str
    created_at: datetime
    updated_at: datetime
    source_count: int
    claim_count: int
    has_report: bool
