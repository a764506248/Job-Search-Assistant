import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('extension popup pairing', () => {
  beforeEach(() => {
    vi.resetModules()
    document.body.innerHTML = `
      <span id="extension-version"></span>
      <p id="status"></p>
      <form id="pair-form">
        <input id="service-url" type="url">
        <input id="pair-code">
        <button id="pair" type="submit">连接</button>
      </form>`
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('pairs from the popup without opening a BOSS tab', async () => {
    const sendMessage = vi.fn(async (message: { type: string }) => {
      if (message.type === 'job-search-assistant:pair') return { ok: true }
      return { connected: true, protocolVersion: '1.0', serviceUrl: 'https://example.com' }
    })
    const createTab = vi.fn()
    vi.stubGlobal('browser', {
      runtime: { sendMessage, getManifest: () => ({ version: '0.4.33' }) },
      storage: { local: { get: vi.fn(async () => ({ browserServiceUrl: 'http://127.0.0.1:8765' })) } },
      tabs: { create: createTab },
    })
    await import('../entrypoints/popup/main')
    const url = document.querySelector<HTMLInputElement>('#service-url')!
    const code = document.querySelector<HTMLInputElement>('#pair-code')!
    url.value = 'https://example.com'
    code.value = '123456'
    document.querySelector<HTMLFormElement>('#pair-form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await vi.waitFor(() => expect(code.value).toBe(''))
    expect(sendMessage).toHaveBeenCalledWith({
      type: 'job-search-assistant:pair', code: '123456', serviceUrl: 'https://example.com',
    })
    expect(createTab).not.toHaveBeenCalled()
    expect(document.querySelector('#extension-version')?.textContent).toBe('v0.4.33')
    expect(document.querySelector('#status')?.textContent).toContain('已连接')
  })

  it('does not submit an invalid code or service address', async () => {
    const sendMessage = vi.fn().mockResolvedValue({ connected: false, protocolVersion: '1.0' })
    vi.stubGlobal('browser', {
      runtime: { sendMessage, getManifest: () => ({ version: '0.4.33' }) },
      storage: { local: { get: vi.fn(async () => ({})) } },
    })
    await import('../entrypoints/popup/main')
    const url = document.querySelector<HTMLInputElement>('#service-url')!
    const code = document.querySelector<HTMLInputElement>('#pair-code')!
    url.value = 'https://example.com'
    code.value = '123'
    document.querySelector<HTMLFormElement>('#pair-form')!.dispatchEvent(new Event('submit', { cancelable: true }))
    await vi.waitFor(() => expect(document.querySelector('#status')?.textContent).toContain('6 位配对码'))
    code.value = '123456'
    url.value = 'ftp://example.com'
    document.querySelector<HTMLFormElement>('#pair-form')!.dispatchEvent(new Event('submit', { cancelable: true }))
    await vi.waitFor(() => expect(document.querySelector('#status')?.textContent).toContain('服务地址'))
    expect(sendMessage).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'job-search-assistant:pair' }))
  })
})
