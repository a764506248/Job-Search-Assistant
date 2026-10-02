export type JsonData = Record<string, any>

export interface HealthResponse {
  status: string
  service: string
  version: string
}

export type SetupCheckStatus = 'ready' | 'pending' | 'warning' | 'blocked'

export interface SetupCheck {
  key: string
  label: string
  status: SetupCheckStatus
  message: string
  blocking: boolean
  actionLabel?: string
  actionPath?: string
}

export interface SetupStatus {
  overall: SetupCheckStatus
  completed: number
  total: number
  checks: SetupCheck[]
  checkedAt: string
}

export interface BrowserProbe {
  webbridgeRunning: boolean
  kimiExtensionConnected: boolean
  projectExtensionReady: boolean
  bossLoggedIn: boolean
  skillVersion: string
  source: 'installer' | 'manual' | 'extension'
  checkedAt?: string
}

export interface SetupTestRunResult {
  ok: boolean
  mode: 'dry-run'
  browserActionsExecuted: boolean
  plannedKeywords: string[]
  dailyTarget: number
  blockingChecks: string[]
  message: string
}

export interface StoredJob {
  id: number
  platformJobId: string
  url: string
  title: string
  companyName: string
  companySize?: string
  location?: string
  workAddress?: string
  salaryText?: string
  experience?: string
  education?: string
  description: string
  skills: string[]
  recruiterName?: string
  recruiterTitle?: string
  capturedAt: string
  source: 'dom' | 'page-state' | 'manual'
  hasCommunicated: boolean
  hasInterview: boolean
  generatedGreeting?: string
  resumeVariant: 'default' | 'optimized'
  generatedResumeId?: number
  resumeOptimization?: string
}

export interface JobTrackingUpdate {
  hasCommunicated: boolean
  hasInterview: boolean
  generatedGreeting?: string
  resumeVariant: 'default' | 'optimized'
  generatedResumeId?: number
  resumeOptimization?: string
}

export interface ManualJobInput {
  title: string
  companyName: string
  companySize?: string
  url?: string
  location?: string
  workAddress?: string
  salaryText?: string
  experience?: string
  education?: string
  description: string
  skills: string[]
  recruiterName?: string
  recruiterTitle?: string
  hasCommunicated?: boolean
  hasInterview?: boolean
  generatedGreeting?: string
  resumeVariant?: 'default' | 'optimized'
  generatedResumeId?: number
  resumeOptimization?: string
}

export interface LibraryRecord {
  id: number
  kind: string
  name: string
  data: JsonData
  createdAt: string
  updatedAt: string
}

export interface RagSearchResult {
  sourceType: string
  sourceId: string
  sourceName: string
  knowledgeType: string
  entityId: string
  tags: string[]
  chunkIndex: number
  content: string
  score: number
  vectorScore: number
  keywordScore: number
}

export interface RagStatus {
  chunks: number
  sources: number
  indexedAt?: string
  model?: string
  embeddingAvailable: boolean
  embeddingService: JsonData
}

export interface RagChunk {
  id: number
  sourceType: string
  sourceId: string
  sourceName: string
  knowledgeType: string
  entityId: string
  tags: string[]
  chunkIndex: number
  content: string
  contentHash: string
  embedding: number[]
  dimensions: number
  model: string
  indexedAt: string
}

export interface JobMatch {
  suitabilityScore: number
  customizationConfidence: number
  decision: { materialStrategy: 'custom' | 'default' | 'blocked' }
  evidence: RagSearchResult[]
}

export interface MaterialPreview {
  jobId: number
  modelRecordId: number
  modelName: string
  modelId: string
  defaultGreeting: string
  greeting: string
  resume: {
    headline: string
    summary: string[]
    skills: string[]
    projects: string[]
    workExperience: string[]
    education: string[]
    optimizationNotes: string[]
  }
  match: JobMatch
}

export interface ResumeTemplate {
  id: string
  name: string
  description: string
  accent: string
}

export interface ResumeImportResult {
  filename: string
  profileFields: string[]
  resumeId: number
  projectIds: number[]
  extractedCharacters: number
  indexRebuilt: boolean
  indexedChunks?: number
  indexError?: string
  aiExtractionUsed: boolean
  aiProjectCount: number
  aiExtractionError?: string
  aiModelRecordId?: number
  aiModelName?: string
  aiModelId?: string
  aiAttemptErrors: string[]
  aiProfileExtracted: boolean
  confirmationRequired: boolean
  confirmationStatus: 'pending' | 'confirmed'
}

export interface ResumeConfirmationResult {
  resume: LibraryRecord
  profileFields: string[]
  projectIds: number[]
  indexRebuilt: boolean
  indexedChunks?: number
  indexError?: string
}
