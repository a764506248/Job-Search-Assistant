import type {
  BrowserProbe,
  BrowserPairing,
  BrowserProtocolStatus,
  AutomationEvent,
  AutomationReport,
  AutomationRun,
  AutomationCollectionConfig,
  HealthResponse,
  JobMatch,
  JobInsight,
  MaterialPreview,
  JobTrackingUpdate,
  LibraryRecord,
  ManualJobInput,
  ResumeConfirmationResult,
  ResumeImportResult,
  ResumeTemplate,
  SetupStatus,
  SetupTestRunResult,
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
  setupStatus: () => request<SetupStatus>('/v1/setup/status'),
  saveBrowserProbe: (probe: BrowserProbe) => request<BrowserProbe>('/v1/setup/browser/probe', json('POST', probe)),
  runSetupTest: () => request<SetupTestRunResult>('/v1/setup/test-run', { method: 'POST' }),
  browserStatus: () => request<BrowserProtocolStatus>('/v1/browser/status'),
  createBrowserPairing: () => request<BrowserPairing>('/v1/browser/pairing', { method: 'POST' }),
  testBrowserConnection: () => request<{ status: string; evidence: Record<string, unknown> }>('/v1/browser/actions/test', json('POST', { action: 'ping', payload: {} })),
  automationRuns: () => request<{ items: AutomationRun[] }>('/v1/automation/runs'),
  createAutomationRun: (targetCount: number, config: AutomationCollectionConfig) => request<AutomationRun>('/v1/automation/runs', json('POST', { targetCount, config })),
  collectAutomationRun: (id: number) => request<AutomationRun>(`/v1/automation/runs/${id}/collect`, { method: 'POST' }),
  automationEvents: (id: number) => request<{ items: AutomationEvent[] }>(`/v1/automation/runs/${id}/events`),
  automationReport: (id: number) => request<AutomationReport>(`/v1/automation/runs/${id}/report`),
  retryAutomationRun: (id: number) => request<AutomationRun>(`/v1/automation/runs/${id}/retry`, { method: 'POST' }),
  controlAutomationRun: (id: number, action: 'start' | 'pause' | 'resume' | 'stop', selectedJobIds?: string[]) => request<AutomationRun>(
    `/v1/automation/runs/${id}/${action}`,
    action === 'start' && selectedJobIds ? json('POST', { selectedJobIds }) : { method: 'POST' },
  ),
  jobs: (options: { page?: number; pageSize?: number; query?: string; communicationResult?: string } = {}) => {
    const params = new URLSearchParams({
      page: String(options.page || 1),
      pageSize: String(options.pageSize || 20),
    })
    if (options.query?.trim()) params.set('query', options.query.trim())
    if (options.communicationResult) params.set('communicationResult', options.communicationResult)
    return request<{ total: number; page: number; pageSize: number; totalPages: number; items: StoredJob[] }>(`/v1/jobs?${params}`)
  },
  createJob: (job: ManualJobInput) => request<StoredJob>('/v1/jobs', json('POST', job)),
  updateJobTracking: (id: number, data: JobTrackingUpdate) => request<StoredJob>(`/v1/jobs/${id}/tracking`, json('PUT', data)),
  deleteJob: (id: number) => request<void>(`/v1/jobs/${id}`, { method: 'DELETE' }),
  matchJob: (job: StoredJob) => request<JobMatch>('/v1/jobs/match', json('POST', {
    title: job.title,
    jobText: job.description,
    skills: job.skills || [],
  })),
  analyzeJob: (id: number, useAi = false, modelRecordId?: number) => request<JobInsight>(`/v1/jobs/${id}/analysis`, json('POST', {
    useAi,
    ...(modelRecordId === undefined ? {} : { modelRecordId }),
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
  confirmResume: (id: number) => request<ResumeConfirmationResult>(`/v1/resumes/${id}/confirm`, { method: 'POST' }),
  setDefaultResumeImage: (id: number) => request<LibraryRecord>(`/v1/resumes/${id}/default-image`, { method: 'PUT' }),
  templates: () => request<{ items: ResumeTemplate[]; sampleData: Record<string, any> }>('/v1/resume-templates'),
}
