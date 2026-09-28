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
