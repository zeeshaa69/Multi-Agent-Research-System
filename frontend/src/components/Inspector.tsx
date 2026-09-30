import { KINDS, formatTime, safeHref } from '../labels'
import { Confidence, KindBadge } from './Badge'
import type { Job, ReportStatement } from '../types'

export function Inspector({
  job,
  statement,
  onClose,
}: {
  job: Job
  statement: ReportStatement
  onClose: () => void
}) {
  const claims = statement.claim_ids
    .map((id) => job.claims.find((c) => c.id === id))
    .filter((c) => c !== undefined)
  const sourceIds = new Set(statement.source_ids)
  const sources = job.sources.filter((s) => sourceIds.has(s.id))
  const related = job.logs.filter((l) => {
    const claimId = l.data['claim_id']
    const sourceId = l.data['source_id']
    return (
      (typeof claimId === 'string' && statement.claim_ids.includes(claimId)) ||
      (typeof sourceId === 'string' && sourceIds.has(sourceId)) ||
      (statement.kind === 'generated_synthesis' && l.agent === 'synthesizer')
    )
  })
  const srcNum = (id: string) => job.sources.findIndex((s) => s.id === id) + 1
  return (
    <aside className="inspector" aria-label="Provenance inspector">
      <header>
        <h3>How was this produced?</h3>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close inspector">
          ×
        </button>
      </header>
      <div className={`quote-box ${KINDS[statement.kind].className}`}>
        <KindBadge kind={statement.kind} />
        <p>{statement.text}</p>
        <Confidence value={statement.confidence} />
      </div>
      <p className="small">{KINDS[statement.kind].explain}</p>

      <h4>1. Claims behind it</h4>
      {claims.length === 0 ? (
        <p className="small muted">
          None. This statement is generated text, not derived from a single source quote.
        </p>
      ) : (
        claims.map((c) => (
          <div key={c.id} className="step">
            <div className="small">
              <strong>{c.verification_status}</strong> · confidence {c.confidence.toFixed(2)} ·{' '}
              {c.supporting_sources.length} supporting source(s)
              {c.conflicting_evidence.length > 0 && ` · ${c.conflicting_evidence.length} conflicting`}
            </div>
            <div className="small">{c.claim}</div>
            {c.notes.length > 0 && <div className="small muted">{c.notes.join(' · ')}</div>}
          </div>
        ))
      )}

      <h4>2. Evidence quotes</h4>
      {claims.flatMap((c) => [
        ...c.supporting_sources.map((r) => (
          <blockquote key={`s-${r.claim_id}`} className="small">
            “{r.quote}”<div className="muted">supports · [S{srcNum(r.source_id)}]</div>
          </blockquote>
        )),
        ...c.conflicting_evidence.map((e) => (
          <blockquote key={`c-${e.claim_id}`} className="small conflict">
            “{e.quote}”
            <div className="muted">
              conflicts · [S{srcNum(e.source_id)}] · {e.reason}
            </div>
          </blockquote>
        )),
      ])}
      {claims.length === 0 && <p className="small muted">No quotes: nothing here is quoted from a source.</p>}

      <h4>3. Sources</h4>
      {sources.length === 0 && <p className="small muted">No sources cited.</p>}
      {sources.map((s) => {
        const href = safeHref(s.url)
        return (
          <div key={s.id} className="step small">
            <strong>
              [S{srcNum(s.id)}] {s.title}
            </strong>
            <div className="muted">{href ? <a href={href} target="_blank" rel="noreferrer noopener">{s.url}</a> : s.url}</div>
            <div className="muted">
              retrieved {formatTime(s.retrieved_at)} · sha256:{s.content_hash.slice(0, 12)}…
            </div>
          </div>
        )
      })}

      <h4>4. Agent activity</h4>
      {related.length === 0 && <p className="small muted">No log entries reference this statement.</p>}
      <ul className="small mini-log">
        {related.slice(0, 12).map((l) => (
          <li key={l.seq}>
            <span className="mono">{l.agent}</span> — {l.message}
          </li>
        ))}
      </ul>
    </aside>
  )
}
