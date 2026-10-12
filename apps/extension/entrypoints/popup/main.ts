const status = document.querySelector<HTMLElement>('#status')!
const openConsole = document.querySelector<HTMLButtonElement>('#open-console')!

async function refreshStatus() {
  const result = await browser.runtime.sendMessage({
    type: 'job-search-assistant:connection-status',
  }) as { connected: boolean, protocolVersion: string }
  status.textContent = result.connected
    ? `已连接 · 协议 ${result.protocolVersion}`
    : '尚未连接本地服务'
  status.classList.toggle('ready', result.connected)
}

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

void refreshStatus()
