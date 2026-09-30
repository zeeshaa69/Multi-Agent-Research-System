import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { Inspector } from './components/Inspector'
import { ClaimsPanel, LogPanel, SourcesPanel } from './components/Panels'
import { Pipeline } from './components/Pipeline'
import { ReportView } from './components/ReportView'
import { Sidebar } from './components/Sidebar'
import type { AppConfig, Job, JobSummary, ReportStatement } from './types'

type Tab = 'report' | 'claims' | 'sources' | 'logs'
const TABS: { id: Tab; label: string }[] = [
  { id: 'report', label: 'Report' },
  { id: 'claims', label: 'Claims' },
  { id: 'sources', label: 'Sources' },
  { id: 'logs', label: 'Agent log' },
]

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [tab, setTab] = useState<Tab>('report')
  const [statement, setStatement] = useState<ReportStatement | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await api.listJobs())
      setError(null)
    } catch {
      setError('Cannot reach the API. Is the backend running?')
    }
  }, [])

  useEffect(() => {
    api.config().then(setConfig).catch(() => undefined)
    void refreshJobs()
    const t = setInterval(() => void refreshJobs(), 2500)
    return () => clearInterval(t)
  }, [refreshJobs])

  const running = job?.status === 'queued' || job?.status === 'running'
  useEffect(() => {
    if (!selected) return
    let cancelled = false
    const load = () =>
      api
        .getJob(selected)
        .then((j) => !cancelled && setJob(j))
        .catch(() => !cancelled && setJob(null))
    void load()
    if (!running && job?.id === selected) return
    const t = setInterval(() => void load(), 1000)
    return () => {
      cancelled = true
      clearInterval(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, running])

  const select = (id: string) => {
    setSelected(id)
    setStatement(null)
    setJob((prev) => (prev?.id === id ? prev : null))
  }

  const create = async (question: string) => {
    const created = await api.createJob(question)
    await refreshJobs()
    select(created.id)
    setTab('report')
  }

  const remove = async (id: string) => {
    await api.deleteJob(id)
    if (selected === id) {
      setSelected(null)
      setJob(null)
    }
    await refreshJobs()
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Multi-Agent Researcher</h1>
        {config && (
          <span className={`pill ${config.mode === 'offline' ? 'pill-offline' : 'pill-live'}`}>
            {config.mode === 'offline'
              ? 'Offline mode · synthetic fixtures · no model'
              : `Live · retrieval: ${config.retrieval} · model: ${config.llm}`}
          </span>
        )}
      </header>
      {error && <div className="banner err" role="alert">{error}</div>}
      <div className="layout">
        <Sidebar jobs={jobs} selected={selected} config={config} onSelect={select} onCreate={create} onDelete={(id) => void remove(id)} />
        <main>
          {!selected || !job || job.id !== selected ? (
            <div className="empty big">
              <h2>{selected ? 'Loading…' : 'Ask a question to start'}</h2>
              {!selected && (
                <p>
                  Seven agents plan, research, extract, fact-check, validate citations, synthesize and write the
                  report. Every statement is labelled as source-supported, uncertain, conflicting or generated
                  synthesis, and you can inspect how each one was produced.
                </p>
              )}
            </div>
          ) : (
            <>
              <section className="job-head">
                <h2>{job.question}</h2>
                <div className="small muted">
                  <span className={`status st-${job.status}`}>{job.status}</span> · {job.sources.length} sources ·{' '}
                  {job.claims.length} claims · job {job.id}
                </div>
                {job.error && <div className="banner err">{job.error}</div>}
                {job.warnings.map((w) => (
                  <div key={w} className="banner warn">{w}</div>
                ))}
              </section>
              <Pipeline job={job} />
              <div className="tabs" role="tablist">
                {TABS.map((t) => (
                  <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'tab active' : 'tab'} onClick={() => setTab(t.id)}>
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="content">
                <div className="panel">
                  {tab === 'report' && <ReportView job={job} selectedId={statement?.id ?? null} onSelect={setStatement} />}
                  {tab === 'claims' && <ClaimsPanel job={job} />}
                  {tab === 'sources' && <SourcesPanel job={job} />}
                  {tab === 'logs' && <LogPanel logs={job.logs} />}
                </div>
                {statement && tab === 'report' && (
                  <Inspector job={job} statement={statement} onClose={() => setStatement(null)} />
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
