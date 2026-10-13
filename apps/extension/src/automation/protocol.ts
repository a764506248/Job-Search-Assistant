export const BROWSER_PROTOCOL_VERSION = '1.0'

export const BROWSER_ACTIONS = [
  'ping',
  'session_status',
  'navigate_search',
  'capture_job',
  'collect_jobs',
  'open_job',
  'open_chat',
  'validate_identity',
  'send_greeting',
  'preview_resume',
  'send_resume',
] as const

export type BrowserAction = typeof BROWSER_ACTIONS[number]

export interface BrowserActionEnvelope {
  requestId: string
  runId: number
  action: BrowserAction
  deadlineMs: number
  payload: Record<string, unknown>
}

export interface BrowserActionResult {
  requestId: string
  status: 'success' | 'failed' | 'blocked' | 'confirmation_required' | 'uncertain'
  evidence: Record<string, unknown>
  error?: string
}

export function isBrowserActionEnvelope(value: unknown): value is BrowserActionEnvelope {
  if (!value || typeof value !== 'object') return false
  const envelope = value as Partial<BrowserActionEnvelope>
  return typeof envelope.requestId === 'string'
    && typeof envelope.runId === 'number'
    && typeof envelope.deadlineMs === 'number'
    && !!envelope.payload
    && typeof envelope.payload === 'object'
    && BROWSER_ACTIONS.includes(envelope.action as BrowserAction)
}
