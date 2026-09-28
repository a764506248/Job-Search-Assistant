import type {
  DecisionRequest,
  DecisionResponse,
  HealthResponse,
  JobCaptureRequest,
  JobCaptureResponse,
  JdAnalysisRequest,
  JdAnalysisResponse,
  JobEvaluationRequest,
  JobEvaluationResponse,
} from '@job-search-assistant/contracts'

const DEFAULT_BASE_URL = 'http://127.0.0.1:8765'

export class LocalServiceClient {
  constructor(
    private readonly baseUrl = DEFAULT_BASE_URL,
    private readonly token?: string,
  ) {}

  health(): Promise<HealthResponse> {
    return this.request('/v1/health', { authenticated: false })
  }

  decide(input: DecisionRequest): Promise<DecisionResponse> {
    return this.request('/v1/decisions/evaluate', {
      method: 'POST',
      body: input,
    })
  }

  captureJobs(input: JobCaptureRequest): Promise<JobCaptureResponse> {
    return this.request('/v1/jobs/capture', {
      method: 'POST',
      body: input,
    })
  }

  analyzeJd(input: JdAnalysisRequest): Promise<JdAnalysisResponse> {
    return this.request('/v1/jd/analyze', {
      method: 'POST',
      body: input,
    })
  }

  evaluateJob(input: JobEvaluationRequest): Promise<JobEvaluationResponse> {
    return this.request('/v1/jobs/evaluate', {
      method: 'POST',
      body: input,
    })
  }

  private async request<T>(
    path: string,
    options: {
      method?: 'GET' | 'POST'
      body?: unknown
      authenticated?: boolean
    } = {},
  ): Promise<T> {
    const headers = new Headers({ Accept: 'application/json' })
    if (options.body !== undefined) headers.set('Content-Type', 'application/json')
    if (options.authenticated !== false && this.token) headers.set('X-Local-Token', this.token)

    const response = await fetch(`${this.baseUrl}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })

    if (!response.ok) {
      throw new Error(`Local service request failed: ${response.status}`)
    }
    return (await response.json()) as T
  }
}
