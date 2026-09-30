import { useState } from 'react'
import { formatTime, safeHref, STATUS_KIND } from '../labels'
import { Confidence, KindBadge } from './Badge'
import type { AgentLogEntry, Claim, Job, Source } from '../types'

function HighlightedText({ source }: { source: Source }) {
  const ranges: [number, number][] = []
  for (const c of source.claims) {
    const at = source.text.indexOf(c.quote)
    if (at >= 0) ranges.push([at, at + c.quote.length])
  }
  ranges.sort((a, b) => a[0] - b[0])
  const parts: React.ReactNode[] = []
  let cursor = 0
  ranges.forEach(([s, e], i) => {
    if (s < cursor) return
    parts.push(source.text.slice(cursor, s))
    parts.push(<mark key={i}>{source.text.slice(s, e)}</mark>)
    cursor = e
  })
  parts.push(source.text.slice(cursor))
  return <pre className="source-text">{parts}</pre>
}

export function SourcesPanel({ job }: { job: Job }) {
  if (job.sources.length === 0) return <div className="empty">No sources retrieved yet.</div>
  return (
    <div className="cards">
      {job.sources.map((s, i) => {
        const href = safeHref(s.url)
        return (
          <article key={s.id} className="card" id={`source-${s.id}`}>
            <header>
              <strong>
                [{i + 1}] {s.title}
              </strong>
              <span className="pill">{s.source_type}</span>
            </header>
            <dl className="meta small">
              <dt>URL</dt>
              <dd>{href ? <a href={href} target="_blank" rel="noreferrer noopener">{s.url}</a> : s.url}</dd>
              <dt>Retrieved</dt>
              <dd>{formatTime(s.retrieved_at)}</dd>
              <dt>Content hash</dt>
              <dd className="mono">sha256:{s.content_hash.slice(0, 16)}…</dd>
              <dt>Claims</dt>
              <dd>{s.claims.length} extracted</dd>
            </dl>
            <details>
              <summary>Extracted text (quotes used as evidence are highlighted)</summary>
              <HighlightedText source={s} />
            </details>
          </article>
        )
      })}
    </div>
  )
}

export function ClaimsPanel({ job }: { job: Job }) {
  const [filter, setFilter] = useState<string>('all')
  const srcIndex = new Map(job.sources.map((s, i) => [s.id, i + 1]))
  const shown = job.claims.filter((c) => filter === 'all' || c.verification_status === filter)
  if (job.claims.length === 0) return <div className="empty">No claims verified yet.</div>
  return (
    <>
      <div className="filters" role="group" aria-label="Filter by verification status">
        {['all', 'supported', 'uncertain', 'conflicting', 'unsupported'].map((f) => (
          <button
            key={f}
            type="button"
            className={filter === f ? 'chip active' : 'chip'}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>
      <div className="cards">
        {shown.map((c) => (
          <ClaimCard key={c.id} claim={c} srcIndex={srcIndex} />
        ))}
      </div>
    </>
  )
}

function ClaimCard({ claim, srcIndex }: { claim: Claim; srcIndex: Map<string, number> }) {
  const kind = STATUS_KIND[claim.verification_status]
  return (
    <article className="card">
      <header>
        {kind ? <KindBadge kind={kind} /> : <span className="badge k-unsupported">✗ Unsupported (excluded)</span>}
        <Confidence value={claim.confidence} />
      </header>
      <p>{claim.claim}</p>
      {claim.supporting_sources.map((r) => (
        <blockquote key={r.claim_id} className="small">
          “{r.quote}” <span className="muted">— [S{srcIndex.get(r.source_id) ?? '?'}]</span>
        </blockquote>
      ))}
      {claim.conflicting_evidence.length > 0 && (
        <div className="conflict-box small">
          <strong>Conflicting evidence</strong>
          {claim.conflicting_evidence.map((e) => (
            <blockquote key={e.claim_id}>
              “{e.quote}” <span className="muted">— [S{srcIndex.get(e.source_id) ?? '?'}] · {e.reason}</span>
            </blockquote>
          ))}
        </div>
      )}
      {claim.notes.length > 0 && <div className="small muted">{claim.notes.join(' · ')}</div>}
    </article>
  )
}

export function LogPanel({ logs }: { logs: AgentLogEntry[] }) {
  if (logs.length === 0) return <div className="empty">No log entries yet.</div>
  return (
    <table className="log">
      <thead>
        <tr>
          <th>#</th>
          <th>Time</th>
          <th>Agent</th>
          <th>Event</th>
          <th>Message</th>
        </tr>
      </thead>
      <tbody>
        {logs.map((l) => (
          <tr key={l.seq} className={`lv-${l.level}`}>
            <td>{l.seq}</td>
            <td className="mono">{new Date(l.ts).toLocaleTimeString()}</td>
            <td>{l.agent}</td>
            <td className="mono">{l.event}</td>
            <td>{l.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
