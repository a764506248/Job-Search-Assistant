const status = document.querySelector<HTMLElement>('#status')!
const openConsole = document.querySelector<HTMLButtonElement>('#open-console')!
const pairForm = document.querySelector<HTMLFormElement>('#pair-form')!
const serviceUrl = document.querySelector<HTMLInputElement>('#service-url')!
const code = document.querySelector<HTMLInputElement>('#pair-code')!
const pair = document.querySelector<HTMLButtonElement>('#pair')!

async function refreshStatus() {
  const result = await browser.runtime.sendMessage({
    type: 'job-search-assistant:connection-status',
  }) as { connected: boolean, protocolVersion: string, serviceUrl?: string }
  status.textContent = result.connected
    ? `${result.serviceUrl ?? '服务'} 已连接 · 协议 ${result.protocolVersion}`
    : '尚未连接服务，请输入地址和配对码'
  status.classList.toggle('ready', result.connected)
}

pairForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  const url = serviceUrl.value.trim()
  if (!/^\d{6}$/.test(code.value.trim())) {
    status.textContent = '请输入 6 位配对码'
    return
  }
  try {
    const parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) throw new Error()
  }
  catch {
    status.textContent = '请输入以 http:// 或 https:// 开头的服务地址'
    return
  }
  pair.disabled = true
  status.classList.remove('ready')
  status.textContent = '正在连接…'
  try {
    await browser.runtime.sendMessage({ type: 'job-search-assistant:pair', code: code.value.trim(), serviceUrl: url })
    const deadline = Date.now() + 10_000
    while (Date.now() < deadline) {
      const result = await browser.runtime.sendMessage({ type: 'job-search-assistant:connection-status' }) as { connected: boolean }
      if (result.connected) {
        code.value = ''
        await refreshStatus()
        return
      }
      await new Promise(resolve => setTimeout(resolve, 250))
    }
    status.textContent = '连接仍在进行中，配对码已提交，无需重复输入'
  }
  catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error)
  }
  finally { pair.disabled = false }
})

openConsole.addEventListener('click', async () => {
  openConsole.disabled = true
  try {
    const tabs = await browser.tabs.query({ url: ['https://zhipin.com/*', 'https://*.zhipin.com/*'] })
    const tab = tabs.find(item => item.active)
      ?? tabs[0]
      ?? await browser.tabs.create({ url: 'https://www.zhipin.com/', active: true })
    if (typeof tab.id !== 'number') throw new Error('无法创建 BOSS 页面，请检查 Chrome 标签页权限')
    await browser.tabs.update(tab.id, { active: true })
    if (typeof tab.windowId === 'number') {
      await browser.windows.update(tab.windowId, { focused: true })
    }
    await openPanelWhenReady(tab.id)
    window.close()
  }
  catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error)
  }
  finally {
    openConsole.disabled = false
  }
})

async function openPanelWhenReady(tabId: number): Promise<void> {
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    try {
      await browser.tabs.sendMessage(tabId, { type: 'job-search-assistant:toggle-control-panel' })
      return
    }
    catch {
      await new Promise(resolve => setTimeout(resolve, 250))
    }
  }
  throw new Error('BOSS 页面已打开，但扩展尚未加载，请刷新页面后重试')
}

void browser.storage.local.get('browserServiceUrl').then((stored) => {
  serviceUrl.value = typeof stored.browserServiceUrl === 'string' ? stored.browserServiceUrl : 'http://127.0.0.1:8765'
})
void refreshStatus().catch((error) => {
  status.textContent = error instanceof Error ? error.message : '扩展后台暂时不可用'
})
