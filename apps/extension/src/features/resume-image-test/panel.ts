const HOST_ID = 'job-search-assistant-image-test-host'
const GET_IMAGE_MESSAGE = 'job-search-assistant:get-default-resume-image'

interface ImageResponse {
  ok: true
  base64: string
  contentType: string
  filename: string
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

export function mountResumeImageTestPanel(doc: Document): void {
  if (doc.getElementById(HOST_ID)) return
  const host = doc.createElement('div')
  host.id = HOST_ID
  host.dataset.version = '0.3.5'
  const shadow = host.attachShadow({ mode: 'open' })
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .panel { position: fixed; right: 16px; bottom: 16px; z-index: 2147483647; width: 246px;
        box-sizing: border-box; padding: 11px; border: 1px solid #d9e2ec; border-radius: 11px;
        background: #fff; box-shadow: 0 10px 32px rgba(15,23,42,.2); color: #172033;
        font: 13px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
      .top { display: flex; align-items: center; gap: 6px; cursor: move; user-select: none; }
      h3 { flex: 1; margin: 0; font-size: 14px; white-space: nowrap; }
      .toggle { width: 28px; height: 26px; margin: 0; padding: 0; background: #eef2f6; color: #344054; font-size: 15px; }
      .compact-actions { display: none; gap: 4px; }
      .compact-actions button { width: auto; margin: 0; padding: 5px 7px; font-size: 11px; white-space: nowrap; }
      .version { margin-top: 2px; color: #667085; font-size: 11px; }
      .paused { margin: 8px 0; padding: 6px 8px; border-radius: 6px; background: #fff7e6; color: #ad6800; }
      .status { margin: 8px 0; min-height: 34px; white-space: pre-wrap; }
      img { display: none; width: 100%; max-height: 150px; object-fit: contain; border: 1px solid #e5e7eb; border-radius: 7px; }
      button { width: 100%; margin-top: 7px; padding: 7px 9px; border: 0; border-radius: 7px;
        background: #00b9b0; color: white; cursor: pointer; font-weight: 600; }
      button.secondary { background: #1677ff; } button:disabled { opacity: .45; cursor: not-allowed; }
      .hint { margin-top: 7px; color: #667085; font-size: 11px; }
      .panel.collapsed { width: 250px; } .panel.collapsed .body { display: none; }
      .panel.collapsed .compact-actions { display: flex; }
    </style>
    <section class="panel">
      <div class="top">
        <h3>简历图片</h3>
        <div class="compact-actions"><button class="compact-load">加载</button><button class="compact-send secondary" disabled>发送</button></div>
        <button class="toggle" title="折叠" aria-label="折叠">−</button>
      </div>
      <div class="body">
        <div class="version">v0.3.5 · visible-send-confirmation · 标题栏可拖拽</div>
        <div class="paused">自动发送仍需用户确认</div>
        <div class="status">请先进入 BOSS 聊天并选中目标联系人。</div>
        <img alt="默认简历图片预览">
        <button class="load">1. 仅加载图片预览</button>
        <button class="send secondary" disabled>2. 确认并发送给当前联系人</button>
        <div class="hint">第二步注入后 BOSS 会立即发送。</div>
      </div>
    </section>`
  doc.documentElement.append(host)

  const status = shadow.querySelector<HTMLElement>('.status')!
  const panel = shadow.querySelector<HTMLElement>('.panel')!
  const dragHandle = shadow.querySelector<HTMLElement>('.top')!
  const toggleButton = shadow.querySelector<HTMLButtonElement>('.toggle')!
  const preview = shadow.querySelector<HTMLImageElement>('img')!
  const loadButton = shadow.querySelector<HTMLButtonElement>('.load')!
  const sendButton = shadow.querySelector<HTMLButtonElement>('.send')!
  const compactLoadButton = shadow.querySelector<HTMLButtonElement>('.compact-load')!
  const compactSendButton = shadow.querySelector<HTMLButtonElement>('.compact-send')!
  let previewUrl: string | undefined
  let pendingFile: File | undefined

  makePanelDraggable(doc, panel, dragHandle)

  toggleButton.addEventListener('click', () => {
    const collapsed = panel.classList.toggle('collapsed')
    toggleButton.textContent = collapsed ? '+' : '−'
    toggleButton.title = collapsed ? '展开' : '折叠'
    toggleButton.setAttribute('aria-label', collapsed ? '展开' : '折叠')
  })

  const loadImage = () => {
    loadButton.disabled = true
    compactLoadButton.disabled = true
    sendButton.disabled = true
    compactSendButton.disabled = true
    status.textContent = '正在从本地服务读取默认简历图片…'
    void loadDefaultImage().then(({ file, url }) => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      previewUrl = url
      pendingFile = file
      preview.src = url
      preview.style.display = 'block'
      status.textContent = `已在扩展内加载 ${file.name}（${formatBytes(file.size)}），尚未发送。\n请核对图片和当前联系人。`
      sendButton.disabled = false
      compactSendButton.disabled = false
    }).catch((error: unknown) => {
      status.textContent = error instanceof Error ? error.message : String(error)
    }).finally(() => {
      loadButton.disabled = false
      compactLoadButton.disabled = false
    })
  }

  const sendImage = () => {
    if (!pendingFile) {
      status.textContent = '请先加载默认简历图片预览。'
      return
    }
    const input = findBossChatImageInput(doc)
    if (!input) {
      status.textContent = '未找到 BOSS 聊天图片上传控件，请进入“消息”页面并选中联系人；当前没有执行发送。'
      return
    }
    putFileIntoInput(input, pendingFile)
    sendButton.disabled = true
    compactSendButton.disabled = true
    status.textContent = '已将图片交给 BOSS 发送，请在聊天记录中确认图片消息已出现。'
  }

  loadButton.addEventListener('click', loadImage)
  compactLoadButton.addEventListener('click', loadImage)
  sendButton.addEventListener('click', sendImage)
  compactSendButton.addEventListener('click', sendImage)
}

export async function loadDefaultImage(): Promise<{ file: File; url: string }> {
  const response = await browser.runtime.sendMessage({ type: GET_IMAGE_MESSAGE }) as ImageResponse
  if (!response?.ok || !response.base64) throw new Error('扩展后台没有返回默认简历图片')
  const binary = atob(response.base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  const file = new File([bytes], response.filename, { type: response.contentType })
  return { file, url: URL.createObjectURL(file) }
}

function formatBytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
