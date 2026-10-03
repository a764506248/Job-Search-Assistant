import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  confirmGreetingSend,
  hasConfirmedPlanApproval,
  resolveGreetingSendApproval,
} from './greeting'

describe('greeting confirmation', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('waits for an explicit in-page confirmation', async () => {
    const decision = confirmGreetingSend('AI 工程师', '示例公司', '您好', 5_000)
    const host = document.getElementById('job-search-assistant-confirm-greeting')!

    host.shadowRoot!.querySelector<HTMLButtonElement>('.confirm')!.click()

    await expect(decision).resolves.toBe('confirmed')
    expect(document.getElementById('job-search-assistant-confirm-greeting')).toBeNull()
  })

  it('renders untrusted message text without creating markup', async () => {
    const decision = confirmGreetingSend('AI 工程师', '示例公司', '<img src=x onerror=alert(1)>', 5_000)
    const host = document.getElementById('job-search-assistant-confirm-greeting')!

    expect(host.shadowRoot!.querySelector('.message')!.textContent).toContain('<img')
    expect(host.shadowRoot!.querySelector('.message img')).toBeNull()
    host.shadowRoot!.querySelector<HTMLButtonElement>('.cancel')!.click()
    await expect(decision).resolves.toBe('cancelled')
  })

  it('recognizes only the server-validated confirmed-plan marker', () => {
    expect(hasConfirmedPlanApproval({ planConfirmed: true })).toBe(true)
    expect(hasConfirmedPlanApproval({ planConfirmed: false })).toBe(false)
    expect(hasConfirmedPlanApproval({ planConfirmed: 'true' })).toBe(false)
    expect(hasConfirmedPlanApproval({ approvalToken: 'not-forwarded-to-extension' })).toBe(false)
    expect(hasConfirmedPlanApproval({})).toBe(false)
  })

  it('skips the per-job modal for a server-validated confirmed plan', async () => {
    const requestInteractiveConfirmation = vi.fn(async () => 'cancelled' as const)

    await expect(resolveGreetingSendApproval(
      { planConfirmed: true },
      requestInteractiveConfirmation,
    )).resolves.toEqual({
      approved: true,
      planApproved: true,
      decision: 'confirmed_plan',
    })
    expect(requestInteractiveConfirmation).not.toHaveBeenCalled()
  })

  it('keeps manual and test calls behind the per-job modal', async () => {
    const requestInteractiveConfirmation = vi.fn(async () => 'confirmed' as const)

    await expect(resolveGreetingSendApproval(
      {},
      requestInteractiveConfirmation,
    )).resolves.toEqual({
      approved: true,
      planApproved: false,
      decision: 'confirmed',
    })
    expect(requestInteractiveConfirmation).toHaveBeenCalledOnce()
  })
})
