const HOST_ID = 'job-search-assistant-control-host'
const GET_IMAGE_MESSAGE = 'job-search-assistant:get-default-resume-image'
const SETTINGS_KEY = 'jobSearchAssistantAutomationSettings'

interface ImageResponse {
  ok: true
  base64: string
  contentType: string
  filename: string
}

export type ResumeSendMode = 'automatic' | 'confirm' | 'off'

export interface AutomationSettings {
  resumeSendMode: ResumeSendMode
  collapsed: boolean
}

const DEFAULT_SETTINGS: AutomationSettings = {
  resumeSendMode: 'automatic',
  collapsed: false,
}

export async function readAutomationSettings(): Promise<AutomationSettings> {
  const stored = await browser.storage.local.get(SETTINGS_KEY)
  const value = stored[SETTINGS_KEY] as Partial<AutomationSettings> | undefined
  return {
    resumeSendMode: ['automatic', 'confirm', 'off'].includes(value?.resumeSendMode ?? '')
      ? value!.resumeSendMode as ResumeSendMode
      : DEFAULT_SETTINGS.resumeSendMode,
    collapsed: value?.collapsed === true,
  }
}

export async function saveAutomationSettings(settings: AutomationSettings): Promise<void> {
  await browser.storage.local.set({ [SETTINGS_KEY]: settings })
}

export function findBossChatImageInput(doc: Document): HTMLInputElement | null {
  const inputs = Array.from(doc.querySelectorAll<HTMLInputElement>('input[type="file"]'))
  return inputs.find((input) => {
    const accept = input.accept.toLowerCase()
    const marker = `${input.id} ${input.name} ${input.getAttribute('ka') ?? ''}`.toLowerCase()
    return accept.includes('image') && !marker.includes('resume-upload')
  }) ?? null
}

export function putFileIntoInput(input: HTMLInputElement, file: File): void {
  const transfer = new DataTransfer()
  transfer.items.add(file)
  input.files = transfer.files
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

export function makePanelDraggable(doc: Document, panel: HTMLElement, handle: HTMLElement): void {
  let dragging = false
  let offsetX = 0
  let offsetY = 0
  handle.addEventListener('mousedown', (event) => {
    const target = event.target
    if (target instanceof Element && target.closest('button')) return
    const rect = panel.getBoundingClientRect()
    dragging = true
    offsetX = event.clientX - rect.left
    offsetY = event.clientY - rect.top
    panel.style.right = 'auto'
    panel.style.bottom = 'auto'
    event.preventDefault()
  })
  doc.addEventListener('mousemove', (event) => {
    if (!dragging) return
    const view = doc.defaultView
    const maxLeft = Math.max(0, (view?.innerWidth ?? 0) - panel.offsetWidth)
    const maxTop = Math.max(0, (view?.innerHeight ?? 0) - panel.offsetHeight)
    panel.style.left = `${Math.min(maxLeft, Math.max(0, event.clientX - offsetX))}px`
    panel.style.top = `${Math.min(maxTop, Math.max(0, event.clientY - offsetY))}px`
  })
  doc.addEventListener('mouseup', () => { dragging = false })
}

export function mountBrowserControlPanel(doc: Document): void {
  if (doc.getElementById(HOST_ID)) return
  const host = doc.createElement('div')
  host.id = HOST_ID
  host.dataset.version = '0.4.11'
  const shadow = host.attachShadow({ mode: 'open' })
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .panel { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; width: 310px;
        box-sizing: border-box; border: 1px solid #cfe0d8; border-radius: 14px; overflow: hidden;
        background: #f8fcfa; box-shadow: 0 16px 46px rgba(15,45,34,.22); color: #17251f;
        font: 13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
      .top { display:flex;align-items:center;gap:8px;padding:12px 14px;background:#0d684f;color:white;cursor:move;user-select:none }
      .brand { flex:1 }.brand strong { display:block;font-size:14px }.brand span { opacity:.78;font-size:10px;letter-spacing:.08em }
      button { border:0;border-radius:8px;cursor:pointer;font:600 13px/1.2 inherit }
      .toggle { width:28px;height:28px;padding:0;background:rgba(255,255,255,.16);color:white;font-size:16px }
      .body { padding:13px }.panel.collapsed { width:218px }.panel.collapsed .body { display:none }
      .status { display:flex;align-items:center;gap:8px;padding:9px 10px;border-radius:9px;background:#fff0df;color:#8b5719 }
      .status.ready { background:#def5e9;color:#0a6a4e }.dot { width:8px;height:8px;border-radius:50%;background:currentColor }
      .pairing { margin-top:11px }.pairing.hidden { display:none }
      label { display:block;margin:0 0 5px;color:#52645c;font-size:11px }
      .service-url { width:100%;box-sizing:border-box;margin-bottom:7px;padding:8px 10px;border:1px solid #bcd2c8;border-radius:8px;font:12px/1.2 inherit }
      .pair-row { display:flex;gap:7px }.pair-row input { min-width:0;flex:1;padding:9px 10px;border:1px solid #bcd2c8;border-radius:8px;font:700 16px/1 monospace;letter-spacing:.18em }
      .primary { padding:9px 12px;background:#087f5f;color:white }.primary:disabled { opacity:.5;cursor:wait }
      .section { margin-top:12px;padding-top:12px;border-top:1px solid #dce8e2 }
      .section-title { margin:0 0 8px;font-size:12px;font-weight:700;color:#31483e }
      .setting { display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-top:8px }
      .setting-text strong { display:block;font-size:12px }.setting-text span { display:block;margin-top:2px;color:#718078;font-size:10px }
      .pill { flex:none;padding:4px 7px;border-radius:999px;background:#def5e9;color:#087356;font-size:10px;font-weight:700 }
      select { max-width:116px;padding:7px 6px;border:1px solid #bcd2c8;border-radius:8px;background:white;color:#17251f;font-size:11px }
      .hint { margin:11px 0 0;color:#6d7d75;font-size:10px;line-height:1.55 }
    </style>
    <section class="panel">
      <header class="top">
        <div class="brand"><strong>自动投递控制台</strong><span>JOB SEARCH ASSISTANT · v0.4.11</span></div>
        <button class="toggle" title="折叠" aria-label="折叠">−</button>
      </header>
      <div class="body">
        <div class="status"><span class="dot"></span><span class="status-text">正在检查本地连接…</span></div>
        <div class="pairing">
          <label for="service-url">服务地址（本地或线上域名）</label>
          <input id="service-url" class="service-url" inputmode="url" placeholder="http://127.0.0.1:8765">
          <label for="pair-code">本地后台显示的 6 位配对码</label>
          <div class="pair-row"><input id="pair-code" inputmode="numeric" maxlength="6" placeholder="000000"><button class="primary pair">连接</button></div>
        </div>
        <div class="section">
          <p class="section-title">发送策略</p>
          <div class="setting"><div class="setting-text"><strong>问候语</strong><span>页面确认投递清单后执行</span></div><span class="pill">自动发送</span></div>
          <div class="setting"><div class="setting-text"><strong>简历图片</strong><span>仅在任务要求发送简历时生效</span></div>
            <select class="resume-mode" aria-label="简历图片发送策略"><option value="automatic">自动发送</option><option value="confirm">发送前确认</option><option value="off">不发送</option></select>
          </div>
        </div>
        <p class="hint">配置保存在本机扩展中。自动发送仍只处理你在本地页面确认过的企业与岗位。</p>
      </div>
    </section>`
  doc.documentElement.append(host)

  const panel = shadow.querySelector<HTMLElement>('.panel')!
  const handle = shadow.querySelector<HTMLElement>('.top')!
  const toggle = shadow.querySelector<HTMLButtonElement>('.toggle')!
  const status = shadow.querySelector<HTMLElement>('.status')!
  const statusText = shadow.querySelector<HTMLElement>('.status-text')!
  const pairing = shadow.querySelector<HTMLElement>('.pairing')!
  const code = shadow.querySelector<HTMLInputElement>('#pair-code')!
  const serviceUrl = shadow.querySelector<HTMLInputElement>('#service-url')!
  const pair = shadow.querySelector<HTMLButtonElement>('.pair')!
  const resumeMode = shadow.querySelector<HTMLSelectElement>('.resume-mode')!
  let settings = { ...DEFAULT_SETTINGS }

  makePanelDraggable(doc, panel, handle)
  const applyCollapsed = (collapsed: boolean) => {
    panel.classList.toggle('collapsed', collapsed)
    toggle.textContent = collapsed ? '+' : '−'
    toggle.title = collapsed ? '展开' : '折叠'
    toggle.setAttribute('aria-label', collapsed ? '展开' : '折叠')
  }
  toggle.addEventListener('click', () => {
    settings.collapsed = !panel.classList.contains('collapsed')
    applyCollapsed(settings.collapsed)
    void saveAutomationSettings(settings)
  })
  resumeMode.addEventListener('change', () => {
    settings.resumeSendMode = resumeMode.value as ResumeSendMode
    void saveAutomationSettings(settings)
  })

  const refreshStatus = async () => {
    try {
      const result = await browser.runtime.sendMessage({ type: 'job-search-assistant:connection-status' }) as { connected: boolean, protocolVersion: string, serviceUrl?: string }
      status.classList.toggle('ready', result.connected)
      statusText.textContent = result.connected
        ? `${result.serviceUrl ?? '服务'} 已连接 · 协议 ${result.protocolVersion}`
        : '尚未连接服务，请检查地址与配对码'
      pairing.classList.remove('hidden')
    }
    catch {
      status.classList.remove('ready')
      statusText.textContent = '扩展后台暂时不可用，请重新加载扩展'
      pairing.classList.remove('hidden')
    }
  }
  pair.addEventListener('click', async () => {
    const value = code.value.trim()
    if (!/^\d{6}$/.test(value)) {
      statusText.textContent = '请输入 6 位配对码'
      return
    }
    pair.disabled = true
    statusText.textContent = '正在连接…'
    try {
      await browser.runtime.sendMessage({ type: 'job-search-assistant:pair', code: value, serviceUrl: serviceUrl.value })
      await new Promise(resolve => setTimeout(resolve, 500))
      await refreshStatus()
    }
    catch (error) { statusText.textContent = error instanceof Error ? error.message : String(error) }
    finally { pair.disabled = false }
  })
  void browser.storage.local.get('browserServiceUrl').then((stored) => {
    serviceUrl.value = typeof stored.browserServiceUrl === 'string' ? stored.browserServiceUrl : 'http://127.0.0.1:8765'
  })
  void readAutomationSettings().then((value) => {
    settings = value
    resumeMode.value = settings.resumeSendMode
    applyCollapsed(settings.collapsed)
  })
  void refreshStatus()
  browser.runtime.onMessage.addListener((message: unknown) => {
    if (!message || typeof message !== 'object' || (message as { type?: unknown }).type !== 'job-search-assistant:toggle-control-panel') return
    settings.collapsed = false
    applyCollapsed(false)
    void saveAutomationSettings(settings)
    return Promise.resolve({ ok: true })
  })
}

export const mountResumeImageTestPanel = mountBrowserControlPanel

export async function loadDefaultImage(): Promise<{ file: File; url: string }> {
  const response = await browser.runtime.sendMessage({ type: GET_IMAGE_MESSAGE }) as ImageResponse
  if (!response?.ok || !response.base64) throw new Error('扩展后台没有返回默认简历图片')
  const binary = atob(response.base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  const file = new File([bytes], response.filename, { type: response.contentType })
  return { file, url: URL.createObjectURL(file) }
}
