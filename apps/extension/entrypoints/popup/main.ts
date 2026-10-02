const status = document.querySelector<HTMLElement>('#status')!
const code = document.querySelector<HTMLInputElement>('#pairing-code')!
const pair = document.querySelector<HTMLButtonElement>('#pair')!

async function refreshStatus() {
  const result = await browser.runtime.sendMessage({
    type: 'job-search-assistant:connection-status',
  }) as { connected: boolean, protocolVersion: string }
  status.textContent = result.connected
    ? `已连接 · 协议 ${result.protocolVersion}`
    : '尚未连接本地服务'
  status.classList.toggle('ready', result.connected)
}

pair.addEventListener('click', async () => {
  const value = code.value.trim()
  if (!/^\d{6}$/.test(value)) {
    status.textContent = '请输入后台生成的 6 位配对码'
    return
  }
  pair.disabled = true
  status.textContent = '正在连接…'
  try {
    await browser.runtime.sendMessage({ type: 'job-search-assistant:pair', code: value })
    await new Promise(resolve => setTimeout(resolve, 500))
    await refreshStatus()
  }
  catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error)
  }
  finally {
    pair.disabled = false
  }
})

void refreshStatus()
