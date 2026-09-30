import { useState } from 'react'
import { formatTime } from '../labels'
import type { AppConfig, JobSummary } from '../types'

interface Props {
  jobs: JobSummary[]
  selected: string | null
  config: AppConfig | null
  onSelect: (id: string) => void
  onCreate: (question: string) => Promise<void>
  onDelete: (id: string) => void
}

const EXAMPLES = [
  'What are the costs, risks and environmental effects of the Harborview Tidal Pilot?',
  'What is the Harborview Tidal Pilot, how much power does it produce, and what does it cost?',
]

function JobItem({ job, selected, onSelect, onDelete }: {
  job: JobSummary
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const active = job.status === 'queued' || job.status === 'running'
  return (
    <li className={selected ? 'job selected' : 'job'}>
      <button type="button" className="job-main" onClick={onSelect}>
        <span className={`dot d-${active ? 'running' : job.status === 'completed' ? 'done' : 'failed'}`} aria-hidden="true" />
        <span className="job-q">{job.question}</span>
        <span className="small muted">
          {job.status} · {job.source_count} sources · {job.claim_count} claims · {formatTime(job.created_at)}
        </span>
      </button>
      {!active && (
        <button type="button" className="icon-btn" onClick={onDelete} aria-label="Delete job">
          🗑
        </button>
      )}
    </li>
  )
}

export function Sidebar({ jobs, selected, config, onSelect, onCreate, onDelete }: Props) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running')
  const history = jobs.filter((j) => !active.includes(j))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onCreate(question.trim())
      setQuestion('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the job.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <nav className="sidebar" aria-label="Research jobs">
      <form onSubmit={submit}>
        <label htmlFor="q">Research question</label>
        <textarea
          id="q"
          rows={4}
          value={question}
          maxLength={1000}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask something the sources can answer…"
        />
        <button type="submit" className="primary" disabled={busy || question.trim().length < 8}>
          {busy ? 'Starting…' : 'Start research'}
        </button>
        {error && <div className="err small" role="alert">{error}</div>}
        {config?.mode === 'offline' && (
          <div className="examples small">
            <span className="muted">Offline fixture examples:</span>
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="link" onClick={() => setQuestion(ex)}>
                {ex}
              </button>
            ))}
          </div>
        )}
      </form>
      <h2>Active jobs</h2>
      {active.length === 0 ? (
        <p className="small muted">Nothing running.</p>
      ) : (
        <ul className="jobs">
          {active.map((j) => (
            <JobItem key={j.id} job={j} selected={j.id === selected} onSelect={() => onSelect(j.id)} onDelete={() => onDelete(j.id)} />
          ))}
        </ul>
      )}
      <h2>Research history</h2>
      {history.length === 0 ? (
        <p className="small muted">No finished jobs yet.</p>
      ) : (
        <ul className="jobs">
          {history.map((j) => (
            <JobItem key={j.id} job={j} selected={j.id === selected} onSelect={() => onSelect(j.id)} onDelete={() => onDelete(j.id)} />
          ))}
        </ul>
      )}
    </nav>
  )
}
