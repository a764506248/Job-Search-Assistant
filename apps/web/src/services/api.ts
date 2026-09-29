import type {
  HealthResponse,
  JobMatch,
  MaterialPreview,
  JobTrackingUpdate,
  LibraryRecord,
  ManualJobInput,
  RagChunk,
  RagSearchResult,
  RagStatus,
  ResumeImportResult,
  ResumeTemplate,
  StoredJob,
} from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Response is not JSON; keep the status based message.
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<HealthResponse>('/v1/health'),
  jobs: () => request<{ total: number; items: StoredJob[] }>('/v1/jobs?limit=500'),
  createJob: (job: ManualJobInput) => request<StoredJob>('/v1/jobs', json('POST', job)),
  updateJobTracking: (id: number, data: JobTrackingUpdate) => request<StoredJob>(`/v1/jobs/${id}/tracking`, json('PUT', data)),
  deleteJob: (id: number) => request<void>(`/v1/jobs/${id}`, { method: 'DELETE' }),
  matchJob: (job: StoredJob) => request<JobMatch>('/v1/jobs/match', json('POST', {
    title: job.title,
    jobText: job.description,
    skills: job.skills || [],
  })),
  previewJobMaterials: (id: number) => request<MaterialPreview>(`/v1/jobs/${id}/material-preview`, json('POST', {})),
  profile: () => request<{ data: Record<string, any> }>('/v1/profile'),
  saveProfile: (data: Record<string, any>) => request<{ data: Record<string, any> }>('/v1/profile', json('PUT', { data })),
  library: (kind: string) => request<{ items: LibraryRecord[] }>(`/v1/library/${kind}`),
  createRecord: (kind: string, name: string, data: Record<string, any>) => request<LibraryRecord>(`/v1/library/${kind}`, json('POST', { name, data })),
  updateRecord: (kind: string, id: number, name: string, data: Record<string, any>) => request<LibraryRecord>(`/v1/library/${kind}/${id}`, json('PUT', { name, data })),
  deleteRecord: (kind: string, id: number) => request<void>(`/v1/library/${kind}/${id}`, { method: 'DELETE' }),
  testModel: (id: number) => request<{ message: string; latencyMs: number }>(`/v1/library/models/${id}/test`, { method: 'POST' }),
  importResume: (file: File, modelRecordId?: number) => {
    const body = new FormData()
    body.append('file', file)
    if (modelRecordId !== undefined) body.append('modelRecordId', String(modelRecordId))
    return request<ResumeImportResult>('/v1/resumes/import', { method: 'POST', body })
  },
  ragStatus: () => request<RagStatus>('/v1/rag/status'),
  ragChunks: () => request<{ total: number; items: RagChunk[] }>('/v1/rag/chunks'),
  deleteRagChunk: (id: number) => request<void>(`/v1/rag/chunks/${id}`, { method: 'DELETE' }),
  rebuildRag: () => request<{ rebuilt: number }>('/v1/rag/rebuild', { method: 'POST' }),
  searchRag: (query: string) => request<{ items: RagSearchResult[] }>('/v1/rag/search', json('POST', { query, limit: 5 })),
  templates: () => request<{ items: ResumeTemplate[]; sampleData: Record<string, any> }>('/v1/resume-templates'),
}
