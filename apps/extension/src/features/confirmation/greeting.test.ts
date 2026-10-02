import { beforeEach, describe, expect, it } from 'vitest'

import { confirmGreetingSend } from './greeting'

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
})
