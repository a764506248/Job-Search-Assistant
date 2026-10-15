const status = document.querySelector<HTMLElement>('#status')!
const version = document.querySelector<HTMLElement>('#extension-version')!
const pairForm = document.querySelector<HTMLFormElement>('#pair-form')!
const serviceUrl = document.querySelector<HTMLInputElement>('#service-url')!
const code = document.querySelector<HTMLInputElement>('#pair-code')!
const pair = document.querySelector<HTMLButtonElement>('#pair')!

version.textContent = `v${browser.runtime.getManifest().version}`

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

void browser.storage.local.get('browserServiceUrl').then((stored) => {
  serviceUrl.value = typeof stored.browserServiceUrl === 'string' ? stored.browserServiceUrl : 'http://127.0.0.1:8765'
})
void refreshStatus().catch((error) => {
  status.textContent = error instanceof Error ? error.message : '扩展后台暂时不可用'
})
