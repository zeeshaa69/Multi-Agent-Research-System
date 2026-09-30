import { STAGES, TASK_STATUS_LABEL } from '../labels'
import type { Job, TaskRecord, TaskStatus } from '../types'

function stageStatus(tasks: TaskRecord[]): TaskStatus {
  if (tasks.length === 0) return 'pending'
  if (tasks.some((t) => t.status === 'failed')) return 'failed'
  if (tasks.some((t) => t.status === 'running')) return 'running'
  if (tasks.every((t) => t.status === 'done')) return 'done'
  if (tasks.every((t) => t.status === 'skipped')) return 'skipped'
  if (tasks.some((t) => t.status === 'done')) return 'running'
  return 'pending'
}

export function Pipeline({ job }: { job: Job }) {
  return (
    <ol className="pipeline" aria-label="Agent pipeline">
      {STAGES.map((stage, i) => {
        const tasks = job.tasks.filter((t) => t.kind === stage.kind)
        const status = stageStatus(tasks)
        const done = tasks.filter((t) => t.status === 'done').length
        const retries = tasks.reduce((n, t) => n + Math.max(0, t.attempts - 1), 0)
        const error = tasks.find((t) => t.error)?.error
        return (
          <li key={stage.kind} className={`stage s-${status}`}>
            <div className="stage-head">
              <span className="stage-index">{i + 1}</span>
              <span className="stage-label">{stage.label}</span>
            </div>
            <div className="stage-agent small muted">{stage.agent}</div>
            <div className="stage-status small">
              <span className={`dot d-${status}`} aria-hidden="true" />
              {TASK_STATUS_LABEL[status]}
              {tasks.length > 1 && ` · ${done}/${tasks.length}`}
            </div>
            {retries > 0 && <div className="small warn">{retries} retr{retries === 1 ? 'y' : 'ies'}</div>}
            {error && (
              <div className="small err" title={error}>
                {error.slice(0, 60)}
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
