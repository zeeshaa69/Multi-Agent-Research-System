export type VerificationStatus = 'supported' | 'uncertain' | 'conflicting' | 'unsupported'
export type StatementKind = 'source_supported' | 'uncertain' | 'conflicting' | 'generated_synthesis'
export type TaskKind =
  | 'plan'
  | 'research'
  | 'extract'
  | 'factcheck'
  | 'validate_citations'
  | 'synthesize'
  | 'write_report'
export type TaskStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface SubQuestion {
  id: string
  text: string
  keywords: string[]
  rationale: string
}

export interface ExtractedClaim {
  id: string
  text: string
  quote: string
  relevance: Record<string, number>
  hedged: boolean
  grounding: 'unchecked' | 'exact' | 'fuzzy' | 'none'
}

export interface Source {
  id: string
  url: string
  title: string
  retrieved_at: string
  text: string
  source_type: string
  content_hash: string
  claims: ExtractedClaim[]
  subquestion_ids: string[]
}

export interface SourceRef {
  source_id: string
  quote: string
  claim_id: string
}

export interface ConflictEvidence {
  source_id: string
  claim_id: string
  statement: string
  quote: string
  reason: string
}

export interface Claim {
  id: string
  claim: string
  supporting_sources: SourceRef[]
  confidence: number
  verification_status: VerificationStatus
  conflicting_evidence: ConflictEvidence[]
  subquestion_ids: string[]
  hedged: boolean
  notes: string[]
}

export interface ReportStatement {
  id: string
  text: string
  kind: StatementKind
  claim_ids: string[]
  source_ids: string[]
  confidence: number | null
}

export interface ReportSection {
  subquestion_id: string
  title: string
  statements: ReportStatement[]
  unanswered: boolean
}

export interface Report {
  job_id: string
  question: string
  generated_at: string
  summary: ReportStatement[]
  sections: ReportSection[]
  excluded_claim_ids: string[]
  source_ids: string[]
  stats: Record<string, number>
  limitations: string[]
  markdown: string
}

export interface TaskRecord {
  id: string
  kind: TaskKind
  agent: string
  deps: string[]
  status: TaskStatus
  attempts: number
  error: string | null
  payload: Record<string, string>
  started_at: string | null
  finished_at: string | null
}

export interface AgentLogEntry {
  seq: number
  ts: string
  agent: string
  task_id: string | null
  level: 'info' | 'warning' | 'error'
  event: string
  message: string
  data: Record<string, unknown>
}

export interface CitationIssue {
  claim_id: string
  source_id: string | null
  problem: string
}

export interface Job {
  id: string
  question: string
  status: JobStatus
  mode: string
  created_at: string
  updated_at: string
  subquestions: SubQuestion[]
  tasks: TaskRecord[]
  sources: Source[]
  claims: Claim[]
  citation_issues: CitationIssue[]
  report: Report | null
  logs: AgentLogEntry[]
  warnings: string[]
  error: string | null
}

export interface JobSummary {
  id: string
  question: string
  status: JobStatus
  mode: string
  created_at: string
  updated_at: string
  source_count: number
  claim_count: number
  has_report: boolean
}

export interface AppConfig {
  mode: string
  retrieval: string
  llm: string
  model: string | null
}
