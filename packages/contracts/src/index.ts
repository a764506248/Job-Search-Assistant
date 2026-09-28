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

export type RequirementLevel = 'required' | 'preferred' | 'neutral' | 'negated' | 'context'
export type RequirementCategory = 'elite_school' | 'education_degree'

export interface TextEvidence {
  text: string
  start: number
  end: number
}

export interface ParsedRequirement {
  category: RequirementCategory
  level: RequirementLevel
  normalizedValue: string
  evidence: TextEvidence
  explanation: string
}

export interface JdAnalysisRequest {
  jobText: string
}

export interface JdAnalysisResponse {
  requirements: ParsedRequirement[]
  riskRequirements: ParsedRequirement[]
  hasRiskSignals: boolean
  parserVersion: string
}

export interface JobEvaluationRequest extends DecisionRequest {
  eliteSchoolAction?: RuleAction
}

export interface JobEvaluationResponse {
  analysis: JdAnalysisResponse
  decision: DecisionResponse
}

export interface RagSearchResult {
  sourceType: string
  sourceId: string
  sourceName: string
  chunkIndex: number
  content: string
  score: number
  vectorScore: number
  keywordScore: number
}

export interface AutomaticJobMatchRequest {
  jobText: string
  title?: string
  skills?: string[]
  minimumSuitabilityScore?: number
  minimumCustomizationConfidence?: number
  rules?: RiskRuleInput[]
  eliteSchoolAction?: RuleAction
  duplicate?: boolean
  companyBlocked?: boolean
}

export interface AutomaticJobMatchResponse {
  analysis: JdAnalysisResponse
  suitabilityScore: number
  customizationConfidence: number
  decision: DecisionResponse
  evidence: RagSearchResult[]
  scoringVersion: string
}
