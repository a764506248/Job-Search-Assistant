export type MaterialStrategy = 'custom' | 'default' | 'blocked'
export type RuleAction = 'notify' | 'reduce_score' | 'use_default_materials' | 'block_delivery'

export interface RiskRuleInput {
  id: string
  name: string
  patterns: string[]
  action: RuleAction
  scorePenalty?: number
  enabled?: boolean
}

export interface RuleMatch {
  ruleId: string
  ruleName: string
  action: RuleAction
  evidence: string[]
}

export interface DecisionRequest {
  jobText: string
  suitabilityScore: number
  customizationConfidence: number
  minimumSuitabilityScore?: number
  minimumCustomizationConfidence?: number
  rules?: RiskRuleInput[]
  duplicate?: boolean
  companyBlocked?: boolean
}

export interface DecisionResponse {
  materialStrategy: MaterialStrategy
  shouldDeliver: boolean
  effectiveSuitabilityScore: number
  reasons: string[]
  ruleMatches: RuleMatch[]
}

export interface HealthResponse {
  status: 'ok'
  service: 'job-search-assistant-local'
  version: string
}

export interface CapturedJob {
  platform: 'boss'
  platformJobId: string
  url: string
  title: string
  companyName: string
  location?: string
  salaryText?: string
  experience?: string
  education?: string
  description: string
  skills: string[]
  recruiterName?: string
  recruiterTitle?: string
  capturedAt: string
  source: 'dom' | 'page-state'
}

export interface JobCaptureRequest {
  jobs: CapturedJob[]
}

export interface JobCaptureResponse {
  accepted: number
  jobIds: string[]
}
