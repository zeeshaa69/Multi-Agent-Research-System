import type { AppConfig, Job, JobSummary } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail) detail = 'The request was not valid.'
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const api = {
  config: () => request<AppConfig>('/api/config'),
  listJobs: () => request<JobSummary[]>('/api/jobs'),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (question: string) =>
    request<JobSummary>('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: 'DELETE' }),
}
