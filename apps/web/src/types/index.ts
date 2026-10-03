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

export interface BrowserProtocolStatus {
  connected: boolean
  paired: boolean
  protocolVersion: string
  extensionVersion?: string
}

export interface BrowserPairing {
  code: string
  expiresAt: string
  protocolVersion: string
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

export interface AutomationRun {
  id: number
  status: string
  configSnapshot: JsonData
  targetCount: number
  successCount: number
  failureCount: number
  currentKeyword?: string
  currentJobId?: string
  runnerId?: string
  heartbeatAt?: string
  stopReason?: string
  createdAt: string
  startedAt?: string
  finishedAt?: string
  updatedAt: string
}

export type AutomationCollectionStatus = 'pending' | 'collecting' | 'ready' | 'no_matches' | 'failed'

export type AutomationCollectionPhase =
  | 'queued'
  | 'searching'
  | 'collecting'
  | 'analyzing'
  | 'analysis_completed'
  | 'awaiting_confirmation'
  | 'failed'

export type AutomationReviewOutcome = 'approved' | 'rule_rejected' | 'duplicate' | 'material_error' | 'analysis_error'

export interface AutomationReviewedJob {
  snapshotId: number | null
  jobId: string
  title: string
  companyName: string
  salaryText: string | null
  location: string | null
  outcome: AutomationReviewOutcome
  suitabilityScore: number | null
  reasons: string[]
  ruleMatches?: JsonData[]
}

export interface AutomationCollectionState {
  status: AutomationCollectionStatus
  source?: 'extension' | 'provided'
  phase?: AutomationCollectionPhase
  queuedAt?: string
  startedAt?: string
  completedAt?: string
  failedAt?: string
  updatedAt?: string
  currentKeyword?: string
  requestedTarget?: number
  candidateLimit?: number
  collectionIntervalMs?: number
  collectionFilters?: AutomationCollectionFilters
  existingExcludedCount?: number
  collectedCount?: number
  analyzedCount?: number
  approvedCount?: number
  rejectedCount?: number
  skippedCount?: number
  ruleRejectedCount?: number
  duplicateCount?: number
  materialErrorCount?: number
  analysisErrorCount?: number
  attemptId?: number
  batchNumber?: number
  batchLimit?: number
  lastBatchCount?: number
  partial?: boolean
  reviewedJobs?: AutomationReviewedJob[]
  message?: string
  reason?: string
  error?: string
}

export interface AutomationCollectionFilters {
  jobType?: string
  salary?: string
  experience?: string
  degree?: string
  industry?: string
  scale?: string
}

export interface AutomationCollectionConfig {
  candidateLimit: number
  collectionIntervalMs: number
  collectionFilters: AutomationCollectionFilters
  searchKeywords?: string[]
  cityCode?: string
}

export interface PlannedAutomationJob {
  jobId: string
  url: string
  title: string
  companyName: string
  greeting?: string
  salaryText?: string
  location?: string
  retrySkipGreeting?: boolean
  retrySkipResume?: boolean
}

export interface AutomationEvent {
  id: number
  runId: number
  sequence: number
  eventType: string
  level: string
  payload: JsonData
  createdAt: string
}

export interface AutomationAction {
  idempotencyKey: string
  runId: number
  jobId: string
  actionType: string
  status: 'pending' | 'succeeded' | 'failed' | 'uncertain'
  attemptCount: number
  lastError?: string
  updatedAt: string
}

export interface AutomationReport {
  run: AutomationRun
  actions: AutomationAction[]
  events: AutomationEvent[]
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

export interface KnowledgeEvidence {
  sourceType: string
  sourceId: string
  sourceName: string
  knowledgeType: string
  entityId: string
  tags: string[]
  chunkIndex: number
  content: string
  score: number
  keywordScore: number
}

export interface JobMatch {
  suitabilityScore: number
  customizationConfidence: number
  decision: { materialStrategy: 'custom' | 'default' | 'blocked' }
  evidence: KnowledgeEvidence[]
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

export interface JobInsight {
  jobId: number
  mode: 'local' | 'ai'
  summary: string
  strengths: string[]
  gaps: string[]
  recommendations: string[]
  interviewQuestions: string[]
  match: JobMatch
  modelRecordId?: number
  modelName?: string
  modelId?: string
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
}
