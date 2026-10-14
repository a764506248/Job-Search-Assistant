export type PlatformOption = { label: string; code?: string | null }

export type CodexDeliveryConfig = {
  id?: number
  name: string
  isDefault: boolean
  enabled: boolean
  sourceTabs: Array<'推荐' | '附近' | '最新'>
  jobIntentions: PlatformOption[]
  keywords: string[]
  cityCode: string | null
  cityName: string | null
  experience: PlatformOption[]
  degree: PlatformOption[]
  companyScale: PlatformOption[]
  bossActivity: PlatformOption | null
  salaryMode: 'all' | 'preset' | 'custom'
  salaryCode: string | null
  salaryMinK: number | null
  salaryMaxK: number | null
  benefits: PlatformOption[]
  financing: PlatformOption[]
  industries: PlatformOption[]
  recommendedTags: PlatformOption[]
  targetDeliveryCount: number
  maxScanCount: number
  intervalSeconds: number
  minimumScore: number
  minimumCustomizationConfidence: number
  resumeId: number | null
  sendResume: boolean
  greetingStrategy: 'custom' | 'default'
  fallbackGreeting: string
  confirmationMode: 'automatic' | 'per_job'
  stopOnUncertain: boolean
  createdAt?: string
  updatedAt?: string
}

export type AgentKeyRecord = {
  id: number
  name: string
  keyPrefix: string
  scopes: string[]
  expiresAt: string | null
  lastUsedAt: string | null
  revokedAt: string | null
  createdAt: string
}

export type CodexDeliveryRun = {
  id: number
  status: string
  currentStage: string
  currentSourceTab: string | null
  currentJobId: string | null
  targetDeliveryCount: number
  scannedCount: number
  capturedCount: number
  analyzedCount: number
  eligibleCount: number
  deliveredCount: number
  skippedCount: number
  failedCount: number
  uncertainCount: number
  stopReason: string | null
  createdAt: string
  steps?: CodexDeliveryStep[]
}

export type CodexDeliveryStep = {
  id: number
  platformJobId: string
  sourceTab: string | null
  listPosition: number | null
  snapshot: Record<string, any> | null
  score: number | null
  greetingConfidence: number | null
  shouldDeliver: boolean | null
  decisionReasons: string[]
  greeting: string | null
  status: string
  evidence: Record<string, any> | null
  errorMessage: string | null
}
