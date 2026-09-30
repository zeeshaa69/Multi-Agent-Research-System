import { Confidence, KindBadge, Legend } from './Badge'
import type { Job, ReportStatement } from '../types'

interface Props {
  job: Job
  selectedId: string | null
  onSelect: (s: ReportStatement) => void
}

function StatementRow({
  st,
  index,
  selected,
  onSelect,
}: {
  st: ReportStatement
  index: Map<string, number>
  selected: boolean
  onSelect: () => void
}) {
  return (
    <li className={`statement ${`kind-${st.kind}`} ${selected ? 'selected' : ''}`}>
      <button type="button" onClick={onSelect} aria-pressed={selected}>
        <div className="statement-top">
          <KindBadge kind={st.kind} />
          <Confidence value={st.confidence} />
        </div>
        <p>{st.text}</p>
        <div className="statement-foot small muted">
          {st.source_ids.length > 0
            ? st.source_ids.map((s) => `[S${index.get(s) ?? '?'}]`).join(' ')
            : 'no direct source'}
          <span className="inspect-hint">Inspect how this was produced →</span>
        </div>
      </button>
    </li>
  )
}

export function ReportView({ job, selectedId, onSelect }: Props) {
  const report = job.report
  if (!report) {
    return (
      <div className="empty">
        {job.status === 'failed'
          ? `No report: ${job.error ?? 'the job failed'}.`
          : 'The report appears here when the pipeline finishes.'}
      </div>
    )
  }
  const index = new Map(report.source_ids.map((id, i) => [id, i + 1]))
  const sourceById = new Map(job.sources.map((s) => [s.id, s]))
  return (
    <div className="report">
      <Legend />
      <h3>Overview</h3>
      <ul className="statements">
        {report.summary.map((st) => (
          <StatementRow
            key={st.id}
            st={st}
            index={index}
            selected={selectedId === st.id}
            onSelect={() => onSelect(st)}
          />
        ))}
      </ul>
      {report.sections.map((sec) => (
        <section key={sec.subquestion_id}>
          <h3>{sec.title}</h3>
          {sec.unanswered ? (
            <p className="muted">No usable evidence was found for this sub-question.</p>
          ) : (
            <ul className="statements">
              {sec.statements.map((st) => (
                <StatementRow
                  key={st.id}
                  st={st}
                  index={index}
                  selected={selectedId === st.id}
                  onSelect={() => onSelect(st)}
                />
              ))}
            </ul>
          )}
        </section>
      ))}
      <h3>Sources cited</h3>
      <ol className="source-list">
        {report.source_ids.map((id) => {
          const s = sourceById.get(id)
          return (
            <li key={id}>
              <strong>{s?.title ?? id}</strong>
              <div className="small muted">{s?.url}</div>
            </li>
          )
        })}
      </ol>
      <h3>Limitations</h3>
      <ul>
        {report.limitations.map((l) => (
          <li key={l} className="small">
            {l}
          </li>
        ))}
      </ul>
      <p>
        <a className="button" href={`/api/jobs/${job.id}/report.md`} target="_blank" rel="noreferrer">
          Open Markdown report
        </a>
      </p>
    </div>
  )
}
