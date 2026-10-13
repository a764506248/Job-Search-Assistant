import { describe, expect, it } from 'vitest'
import { isBrowserActionEnvelope } from './protocol'

describe('browser action protocol', () => {
  it('accepts a supported request envelope', () => {
    expect(isBrowserActionEnvelope({
      requestId: 'request-1', runId: 1, action: 'ping', deadlineMs: 5000, payload: {},
    })).toBe(true)
  })

  it('rejects unknown actions', () => {
    expect(isBrowserActionEnvelope({
      requestId: 'request-1', runId: 1, action: 'arbitrary_js', deadlineMs: 5000, payload: {},
    })).toBe(false)
  })
})
