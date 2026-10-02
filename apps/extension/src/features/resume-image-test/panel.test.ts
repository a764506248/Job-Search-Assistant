import { afterEach, describe, expect, it } from 'vitest'
import { findBossChatImageInput, makePanelDraggable, mountResumeImageTestPanel } from './panel'

describe('resume image test panel', () => {
  afterEach(() => { document.documentElement.innerHTML = '<head></head><body></body>' })

  it('selects the chat image input instead of resume-library inputs', () => {
    document.body.innerHTML = `
      <input type="file" accept=".pdf,.doc" ka="user-resume-upload-file">
      <input id="chat-image" type="file" accept="image/gif,image/jpeg,image/png">
      <input type="file" accept="image/png" ka="user-resume-upload-file">`
    expect(findBossChatImageInput(document)?.id).toBe('chat-image')
  })

  it('mounts the paused test-only interface once', () => {
    mountResumeImageTestPanel(document)
    mountResumeImageTestPanel(document)
    const hosts = document.querySelectorAll('#job-search-assistant-image-test-host')
    expect(hosts).toHaveLength(1)
    expect(hosts[0]?.shadowRoot?.textContent).toContain('自动发送仍需用户确认')
    expect(hosts[0]?.shadowRoot?.textContent).toContain('v0.3.4')
    expect(hosts[0]?.shadowRoot?.textContent).toContain('仅加载图片预览')
  })

  it('can collapse and expand the compact panel', () => {
    mountResumeImageTestPanel(document)
    const shadow = document.querySelector('#job-search-assistant-image-test-host')?.shadowRoot
    const panel = shadow?.querySelector('.panel')
    const toggle = shadow?.querySelector<HTMLButtonElement>('.toggle')
    toggle?.click()
    expect(panel?.classList.contains('collapsed')).toBe(true)
    expect(toggle?.getAttribute('aria-label')).toBe('展开')
    expect(shadow?.querySelector('.compact-load')?.textContent).toBe('加载')
    expect(shadow?.querySelector('.compact-send')?.textContent).toBe('发送')
    expect(shadow?.querySelector('.load')).toBeTruthy()
    expect(shadow?.querySelector('.send')).toBeTruthy()
    toggle?.click()
    expect(panel?.classList.contains('collapsed')).toBe(false)
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
