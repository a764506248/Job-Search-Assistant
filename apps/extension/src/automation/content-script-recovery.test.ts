import { describe, expect, it, vi } from 'vitest'
import {
  canReloadAndRetryAction,
  reloadContentScriptAndRetryOnce,
} from './content-script-recovery'

describe('content script recovery', () => {
  it.each(['session_status', 'capture_job', 'collect_jobs', 'validate_identity'] as const)(
    'allows reload recovery for read-only action %s',
    (action) => expect(canReloadAndRetryAction(action)).toBe(true),
  )

  it.each(['open_chat', 'send_greeting', 'send_resume'] as const)(
    'never automatically retries side-effect action %s',
    (action) => expect(canReloadAndRetryAction(action)).toBe(false),
  )

  it('reloads, waits for the receiver, then retries the original action exactly once', async () => {
    const calls: string[] = []
    const retryOnce = vi.fn(async () => {
      calls.push('retry')
      return { status: 'success' as const, evidence: { recovered: true } }
    })

    const result = await reloadContentScriptAndRetryOnce('collect_jobs', {
      reloadAndWaitForComplete: async () => { calls.push('reload') },
      waitForReceiver: async () => { calls.push('receiver') },
      retryOnce,
    })

    expect(calls).toEqual(['reload', 'receiver', 'retry'])
    expect(retryOnce).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ status: 'success', evidence: { recovered: true } })
  })

  it('does not invoke any recovery step for a side-effect action', async () => {
    const driver = {
      reloadAndWaitForComplete: vi.fn(async () => undefined),
      waitForReceiver: vi.fn(async () => undefined),
      retryOnce: vi.fn(async () => ({ status: 'success' as const, evidence: {} })),
    }

    await expect(reloadContentScriptAndRetryOnce('send_greeting', driver))
      .rejects.toThrow('not safe')
    expect(driver.reloadAndWaitForComplete).not.toHaveBeenCalled()
    expect(driver.waitForReceiver).not.toHaveBeenCalled()
    expect(driver.retryOnce).not.toHaveBeenCalled()
  })
})
