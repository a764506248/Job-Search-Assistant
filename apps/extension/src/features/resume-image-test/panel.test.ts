import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  findBossChatImageInput,
  makePanelDraggable,
  mountBrowserControlPanel,
  readAutomationSettings,
} from './panel'

describe('browser control panel', () => {
  const storage: Record<string, unknown> = {}
  beforeEach(() => {
    for (const key of Object.keys(storage)) delete storage[key]
    vi.stubGlobal('browser', {
      runtime: {
        sendMessage: vi.fn().mockResolvedValue({ connected: true, protocolVersion: '1.0' }),
        onMessage: { addListener: vi.fn() },
      },
      storage: {
        local: {
          get: vi.fn(async (key: string) => ({ [key]: storage[key] })),
          set: vi.fn(async (value: Record<string, unknown>) => { Object.assign(storage, value) }),
        },
      },
    })
  })
  afterEach(() => {
    document.documentElement.innerHTML = '<head></head><body></body>'
    vi.unstubAllGlobals()
  })

  it('selects the chat image input instead of resume-library inputs', () => {
    document.body.innerHTML = `
      <input type="file" accept=".pdf,.doc" ka="user-resume-upload-file">
      <input id="chat-image" type="file" accept="image/gif,image/jpeg,image/png">
      <input type="file" accept="image/png" ka="user-resume-upload-file">`
    expect(findBossChatImageInput(document)?.id).toBe('chat-image')
  })

  it('mounts one unified connection and automation settings panel', () => {
    mountBrowserControlPanel(document)
    mountBrowserControlPanel(document)
    const hosts = document.querySelectorAll('#job-search-assistant-control-host')
    expect(hosts).toHaveLength(1)
    expect(hosts[0]?.shadowRoot?.textContent).toContain('自动投递控制台')
    expect(hosts[0]?.shadowRoot?.textContent).toContain('v0.4.15')
    expect(hosts[0]?.shadowRoot?.textContent).toContain('自动发送')
    expect(hosts[0]?.shadowRoot?.textContent).not.toContain('仅加载图片预览')
  })

  it('can collapse and expand the unified panel', () => {
    mountBrowserControlPanel(document)
    const shadow = document.querySelector('#job-search-assistant-control-host')?.shadowRoot
    const panel = shadow?.querySelector('.panel')
    const toggle = shadow?.querySelector<HTMLButtonElement>('.toggle')
    toggle?.click()
    expect(panel?.classList.contains('collapsed')).toBe(true)
    expect(toggle?.getAttribute('aria-label')).toBe('展开')
    toggle?.click()
    expect(panel?.classList.contains('collapsed')).toBe(false)
  })

  it('defaults resume delivery to automatic and persists the selected mode', async () => {
    expect(await readAutomationSettings()).toMatchObject({ resumeSendMode: 'automatic' })
    mountBrowserControlPanel(document)
    await Promise.resolve()
    const select = document.querySelector('#job-search-assistant-control-host')?.shadowRoot
      ?.querySelector<HTMLSelectElement>('.resume-mode')
    expect(select?.value).toBe('automatic')
    if (select) {
      select.value = 'off'
      select.dispatchEvent(new Event('change'))
    }
    await Promise.resolve()
    expect(await readAutomationSettings()).toMatchObject({ resumeSendMode: 'off' })
  })

  it('drags the panel from its header but ignores header buttons', () => {
    const panel = document.createElement('section')
    const handle = document.createElement('header')
    const button = document.createElement('button')
    handle.append(button)
    panel.append(handle)
    document.body.append(panel)
    Object.defineProperty(panel, 'offsetWidth', { value: 200 })
    Object.defineProperty(panel, 'offsetHeight', { value: 100 })
    panel.getBoundingClientRect = () => ({ left: 20, top: 30, right: 220, bottom: 130, width: 200, height: 100, x: 20, y: 30, toJSON: () => ({}) })
    makePanelDraggable(document, panel, handle)

    handle.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: 40, clientY: 50 }))
    document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 140, clientY: 150 }))
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    expect(panel.style.left).toBe('120px')
    expect(panel.style.top).toBe('130px')

    button.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: 50, clientY: 60 }))
    document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 200, clientY: 200 }))
    expect(panel.style.left).toBe('120px')
  })
})
