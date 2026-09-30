import type { StatementKind, TaskKind, TaskStatus, VerificationStatus } from './types'

export interface KindInfo {
  label: string
  icon: string
  className: string
  explain: string
}

export const KINDS: Record<StatementKind, KindInfo> = {
  source_supported: {
    label: 'Source-supported',
    icon: '✓',
    className: 'k-supported',
    explain:
      'Taken word for word from a source. The quote was found in the stored source text and no retrieved source contradicts it.',
  },
  uncertain: {
    label: 'Uncertain',
    icon: '?',
    className: 'k-uncertain',
    explain:
      'A source says this, but only with hedged wording ("may", "suggests") or an inexact quote match. Treat it as unconfirmed.',
  },
  conflicting: {
    label: 'Conflicting',
    icon: '≠',
    className: 'k-conflicting',
    explain:
      'Retrieved sources disagree (different figures, or one denies what another asserts). Both sides are shown; none is presented as fact.',
  },
  generated_synthesis: {
    label: 'Generated synthesis',
    icon: '✦',
    className: 'k-synthesis',
    explain:
      'Connective text written by the system, not quoted from a source. It summarises counts or (in model mode) verified statements and is not itself source-verified.',
  },
}

export const STATUS_KIND: Record<VerificationStatus, StatementKind | null> = {
  supported: 'source_supported',
  uncertain: 'uncertain',
  conflicting: 'conflicting',
  unsupported: null,
}

export const STAGES: { kind: TaskKind; label: string; agent: string }[] = [
  { kind: 'plan', label: 'Plan', agent: 'Planner' },
  { kind: 'research', label: 'Research', agent: 'Research agents (parallel)' },
  { kind: 'extract', label: 'Extract', agent: 'Extraction agents' },
  { kind: 'factcheck', label: 'Fact-check', agent: 'Fact checker' },
  { kind: 'validate_citations', label: 'Validate citations', agent: 'Citation validator' },
  { kind: 'synthesize', label: 'Synthesize', agent: 'Synthesis agent' },
  { kind: 'write_report', label: 'Write report', agent: 'Report writer' },
]

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  pending: 'Waiting',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  skipped: 'Skipped',
}

export function safeHref(url: string): string | undefined {
  return /^https?:\/\//i.test(url) ? url : undefined
}

export function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
