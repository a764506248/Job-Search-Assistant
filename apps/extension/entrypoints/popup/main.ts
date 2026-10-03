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
    const tab = tabs.find(item => item.active) ?? tabs[0]
    if (!tab?.id) throw new Error('请先打开 BOSS 直聘页面')
    await browser.tabs.update(tab.id, { active: true })
    await browser.tabs.sendMessage(tab.id, { type: 'job-search-assistant:toggle-control-panel' })
    window.close()
  }
  catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error)
  }
  finally {
    openConsole.disabled = false
  }
})

void refreshStatus()
