import {
  BROWSER_PROTOCOL_VERSION,
  isBrowserActionEnvelope,
  type BrowserActionEnvelope,
  type BrowserActionResult,
} from '../src/automation/protocol'
import { buildBossSearchUrl, normalizeBossSearchFilters } from '../src/platform/boss/search'
import {
  canReloadAndRetryAction,
  reloadContentScriptAndRetryOnce,
} from '../src/automation/content-script-recovery'
import { isClosedMessageChannel, isMissingMessageReceiver } from '../src/automation/message-channel'

const DEFAULT_SERVICE_URL = 'http://127.0.0.1:8765'
const TOKEN_KEY = 'browserProtocolToken'
const PAIRING_CODE_KEY = 'browserPairingCode'
const SERVICE_URL_KEY = 'browserServiceUrl'

function normalizeServiceUrl(value: unknown): string {
  const raw = typeof value === 'string' && value.trim() ? value.trim() : DEFAULT_SERVICE_URL
  try {
    const url = new URL(raw)
    if (!['http:', 'https:'].includes(url.protocol)) return DEFAULT_SERVICE_URL
    return `${url.protocol}//${url.host}`
  }
  catch {
    return DEFAULT_SERVICE_URL
  }
}

function websocketUrl(serviceUrl: string): string {
  const url = new URL(serviceUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/v1/browser/ws'
  url.search = ''
  return url.toString()
}

export default defineBackground(() => {
  let socket: WebSocket | undefined
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  let keepaliveTimer: ReturnType<typeof setInterval> | undefined
  let retryMs = 1000

  const connect = async () => {
    if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return
    const stored = await browser.storage.local.get([TOKEN_KEY, PAIRING_CODE_KEY, SERVICE_URL_KEY])
    const token = typeof stored[TOKEN_KEY] === 'string' ? stored[TOKEN_KEY] : ''
    const pairingCode = typeof stored[PAIRING_CODE_KEY] === 'string' ? stored[PAIRING_CODE_KEY] : ''
    const serviceUrl = normalizeServiceUrl(stored[SERVICE_URL_KEY])
    if (!token && !pairingCode) return
    socket = new WebSocket(websocketUrl(serviceUrl))
    socket.addEventListener('open', () => {
      socket?.send(JSON.stringify({
        type: 'hello', token, pairingCode,
        protocolVersion: BROWSER_PROTOCOL_VERSION,
        extensionVersion: browser.runtime.getManifest().version,
      }))
      if (keepaliveTimer) clearInterval(keepaliveTimer)
      keepaliveTimer = setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'keepalive', sentAt: Date.now() }))
        }
      }, 20_000)
    })
    socket.addEventListener('message', async (event) => {
      const message: unknown = JSON.parse(String(event.data))
      if (isPairedMessage(message)) {
        await browser.storage.local.set({ [TOKEN_KEY]: message.token })
        await browser.storage.local.remove(PAIRING_CODE_KEY)
        retryMs = 1000
        return
      }
      if (isReadyMessage(message)) {
        retryMs = 1000
        return
      }
      if (!isBrowserActionEnvelope(message)) return
      const result = await executeBrowserAction(message)
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(result))
    })
    socket.addEventListener('close', scheduleReconnect)
    socket.addEventListener('error', () => socket?.close())
  }

  const scheduleReconnect = () => {
    socket = undefined
    if (keepaliveTimer) clearInterval(keepaliveTimer)
    keepaliveTimer = undefined
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => void connect(), retryMs)
    retryMs = Math.min(retryMs * 2, 30_000)
  }

  browser.runtime.onMessage.addListener(async (message: unknown) => {
    if (isDefaultResumeImageRequest(message)) return fetchDefaultResumeImage()
    if (isPairingRequest(message)) {
      return browser.storage.local
        .set({ [PAIRING_CODE_KEY]: message.code, [SERVICE_URL_KEY]: normalizeServiceUrl(message.serviceUrl) })
        .then(() => browser.storage.local.remove(TOKEN_KEY))
        .then(() => { socket?.close(); return connect() })
        .then(() => ({ ok: true }))
    }
    if (isConnectionStatusRequest(message)) {
      return {
        connected: socket?.readyState === WebSocket.OPEN,
        protocolVersion: BROWSER_PROTOCOL_VERSION,
        serviceUrl: normalizeServiceUrl((await browser.storage.local.get(SERVICE_URL_KEY))[SERVICE_URL_KEY]),
      }
    }
  })
  void connect()
})

async function executeBrowserAction(envelope: BrowserActionEnvelope): Promise<BrowserActionResult> {
  if (envelope.action === 'ping') {
    return success(envelope, { extensionAlive: true, protocolVersion: BROWSER_PROTOCOL_VERSION })
  }
  const tabs = await browser.tabs.query({ url: ['https://zhipin.com/*', 'https://*.zhipin.com/*'] })
  let tab = tabs.find(item => item.active) ?? tabs[0]
  if (!tab?.id && ['session_status', 'navigate_search'].includes(envelope.action)) {
    tab = await browser.tabs.create({ url: 'https://www.zhipin.com/', active: true })
    if (tab.id) await waitForTabReady(tab.id, 'https://www.zhipin.com/')
  }
  if (!tab?.id) return failure(envelope, '没有找到可操作的 BOSS 页面')
  try {
    if (envelope.action === 'navigate_search') {
      const query = String(envelope.payload.query ?? '').trim()
      const city = String(envelope.payload.cityCode ?? '').trim()
      if (!query) return failure(envelope, '搜索关键词不能为空')
      const url = buildBossSearchUrl(
        query,
        city,
        normalizeBossSearchFilters(envelope.payload.filters),
      )
      if (!sameNavigationTarget(tab.url, url)) {
        const ready = waitForTabReady(tab.id, url)
        await browser.tabs.update(tab.id, { url })
        await ready
      }
      return success(envelope, { navigationCompleted: true, url })
    }
    if (envelope.action === 'open_job') {
      const url = new URL(String(envelope.payload.url ?? ''))
      if (url.protocol !== 'https:' || !/(^|\.)zhipin\.com$/.test(url.hostname)) {
        return failure(envelope, '仅允许打开 BOSS 直聘 HTTPS 地址')
      }
      const targetUrl = url.toString()
      if (!sameNavigationTarget(tab.url, targetUrl)) {
        const ready = waitForTabReady(tab.id, targetUrl)
        await browser.tabs.update(tab.id, { url: targetUrl })
        await ready
      }
      return success(envelope, { navigationCompleted: true, url: url.toString() })
    }
    try {
      const result = await sendBrowserActionToTab(tab.id, envelope)
      return { requestId: envelope.requestId, ...result }
    }
    catch (error) {
      if (
        (isMissingMessageReceiver(error) || isClosedMessageChannel(error))
        && canReloadAndRetryAction(envelope.action)
        && tab.url
      ) {
        const recoveryDeadlineAt = Date.now() + Math.max(500, envelope.deadlineMs - 500)
        const result = await reloadContentScriptAndRetryOnce(envelope.action, {
          reloadAndWaitForComplete: () => reloadTabAndWaitForReady(
            tab.id!,
            tab.url!,
            remainingTime(recoveryDeadlineAt, 20_000),
          ),
          waitForReceiver: () => waitForContentScriptReceiver(
            tab.id!,
            envelope,
            recoveryDeadlineAt,
          ),
          retryOnce: () => sendBrowserActionToTab(tab.id!, {
            ...envelope,
            deadlineMs: remainingTime(recoveryDeadlineAt, envelope.deadlineMs),
          }),
        })
        return {
          requestId: envelope.requestId,
          ...result,
          evidence: { ...result.evidence, contentScriptReloaded: true },
        }
      }
      if (envelope.action === 'open_chat' && isClosedMessageChannel(error)) {
        return await recoverOpenChatAfterNavigation(tab.id, envelope)
      }
      throw error
    }
  }
  catch (error) {
    return failure(envelope, error instanceof Error ? error.message : String(error))
  }
}

async function sendBrowserActionToTab(
  tabId: number,
  envelope: BrowserActionEnvelope,
): Promise<Omit<BrowserActionResult, 'requestId'>> {
  return browser.tabs.sendMessage(tabId, {
    type: 'job-search-assistant:browser-action', envelope,
  }) as Promise<Omit<BrowserActionResult, 'requestId'>>
}

async function reloadTabAndWaitForReady(
  tabId: number,
  expectedUrl: string,
  timeoutMs: number,
): Promise<void> {
  const expected = new URL(expectedUrl)
  await new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer)
      browser.tabs.onUpdated.removeListener(listener)
    }
    const timer = setTimeout(() => {
      cleanup()
      reject(new Error('重新加载 BOSS 页面超时，内容脚本未就绪'))
    }, timeoutMs)
    const listener: Parameters<typeof browser.tabs.onUpdated.addListener>[0] = (
      updatedTabId,
      _changeInfo,
      updatedTab,
    ) => {
      if (updatedTabId !== tabId || updatedTab.status !== 'complete' || !updatedTab.url) return
      const actual = new URL(updatedTab.url)
      if (actual.hostname !== expected.hostname || actual.pathname !== expected.pathname) return
      cleanup()
      resolve()
    }
    browser.tabs.onUpdated.addListener(listener)
    void browser.tabs.reload(tabId).catch((error) => {
      cleanup()
      reject(error)
    })
  })
}

async function waitForContentScriptReceiver(
  tabId: number,
  envelope: BrowserActionEnvelope,
  deadlineAt: number,
): Promise<void> {
  const probe: BrowserActionEnvelope = {
    ...envelope,
    requestId: `${envelope.requestId}:content-script-probe`,
    action: 'session_status',
    deadlineMs: remainingTime(deadlineAt, 5_000),
    payload: {},
  }
  let lastError: unknown
  while (Date.now() < deadlineAt) {
    try {
      await sendBrowserActionToTab(tabId, probe)
      return
    }
    catch (error) {
      if (!isMissingMessageReceiver(error)) throw error
      lastError = error
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error('BOSS 页面已重新加载，但内容脚本仍未就绪')
}

function remainingTime(deadlineAt: number, maximumMs: number): number {
  return Math.max(1, Math.min(maximumMs, deadlineAt - Date.now()))
}

function sameNavigationTarget(currentUrl: string | undefined, targetUrl: string): boolean {
  if (!currentUrl) return false
  try {
    const current = new URL(currentUrl)
    const target = new URL(targetUrl)
    return current.origin === target.origin
      && current.pathname === target.pathname
      && current.search === target.search
  }
  catch {
    return false
  }
}

async function recoverOpenChatAfterNavigation(
  tabId: number,
  envelope: BrowserActionEnvelope,
): Promise<BrowserActionResult> {
  const deadline = Date.now() + Math.min(envelope.deadlineMs, 12_000)
  const validationEnvelope: BrowserActionEnvelope = {
    ...envelope,
    action: 'validate_identity',
    payload: { ...envelope.payload, requireChat: true },
  }
  let lastResult: Omit<BrowserActionResult, 'requestId'> | undefined

  while (Date.now() < deadline) {
    try {
      lastResult = await sendBrowserActionToTab(tabId, validationEnvelope)
      if (lastResult.status === 'success') {
        return success(envelope, {
          ...lastResult.evidence,
          chatOpened: true,
          recoveredAfterNavigation: true,
        })
      }
    }
    catch (error) {
      if (!isClosedMessageChannel(error)) throw error
    }
    await new Promise(resolve => setTimeout(resolve, 250))
  }

  return {
    requestId: envelope.requestId,
    status: 'blocked',
    evidence: {
      ...(lastResult?.evidence ?? {}),
      chatOpened: false,
      sideEffectExecuted: true,
      recoveredAfterNavigation: false,
    },
    error: lastResult?.error ?? '已点击沟通入口，但页面跳转后未能确认目标岗位聊天页',
  }
}

async function waitForTabReady(tabId: number, expectedUrl: string, timeoutMs = 20_000): Promise<void> {
  const expected = new URL(expectedUrl)
  const isReady = (tab: { status?: string; url?: string }) => {
    if (tab.status !== 'complete' || !tab.url) return false
    const actual = new URL(tab.url)
    return actual.hostname === expected.hostname && actual.pathname === expected.pathname
  }
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      browser.tabs.onUpdated.removeListener(listener)
      reject(new Error('BOSS 页面加载超时，未继续执行后续操作'))
    }, timeoutMs)
    const listener: Parameters<typeof browser.tabs.onUpdated.addListener>[0] = (updatedTabId, _changeInfo, updatedTab) => {
      if (updatedTabId !== tabId || !isReady(updatedTab)) return
      clearTimeout(timer)
      browser.tabs.onUpdated.removeListener(listener)
      resolve()
    }
    browser.tabs.onUpdated.addListener(listener)
  })
}

function success(
  envelope: BrowserActionEnvelope,
  evidence: Record<string, unknown>,
): BrowserActionResult {
  return { requestId: envelope.requestId, status: 'success', evidence }
}

function failure(envelope: BrowserActionEnvelope, error: string): BrowserActionResult {
  return { requestId: envelope.requestId, status: 'failed', evidence: {}, error }
}

interface DefaultResumeImageRequest {
  type: 'job-search-assistant:get-default-resume-image'
}

interface DefaultResumeImageResponse {
  ok: true
  base64: string
  contentType: string
  filename: string
}

function isPairingRequest(message: unknown): message is { type: 'job-search-assistant:pair'; code: string; serviceUrl?: string } {
  const request = message as { type?: unknown, code?: unknown, serviceUrl?: unknown }
  return !!request && request.type === 'job-search-assistant:pair' && typeof request.code === 'string'
}

function isConnectionStatusRequest(message: unknown): boolean {
  return !!message && typeof message === 'object'
    && (message as { type?: unknown }).type === 'job-search-assistant:connection-status'
}

function isPairedMessage(message: unknown): message is { type: 'paired'; token: string } {
  const response = message as { type?: unknown, token?: unknown }
  return !!response && response.type === 'paired' && typeof response.token === 'string'
}

function isReadyMessage(message: unknown): message is { type: 'ready' } {
  return !!message && typeof message === 'object'
    && (message as { type?: unknown }).type === 'ready'
}

function isDefaultResumeImageRequest(message: unknown): message is DefaultResumeImageRequest {
  return typeof message === 'object'
    && message !== null
    && (message as { type?: unknown }).type === 'job-search-assistant:get-default-resume-image'
}

async function fetchDefaultResumeImage(): Promise<DefaultResumeImageResponse> {
  const stored = await browser.storage.local.get(SERVICE_URL_KEY)
  const serviceUrl = normalizeServiceUrl(stored[SERVICE_URL_KEY])
  const response = await fetch(`${serviceUrl}/v1/resumes/default-image`, {
    headers: { Accept: 'image/png,image/jpeg,image/*' },
  })
  if (!response.ok) throw new Error(`默认简历图片读取失败：HTTP ${response.status}`)

  const contentType = response.headers.get('content-type')?.split(';')[0] || 'image/png'
  if (!contentType.startsWith('image/')) throw new Error(`默认简历接口返回的不是图片：${contentType}`)

  const filename = parseFilename(response.headers.get('content-disposition'))
    ?? `default-resume.${contentType === 'image/jpeg' ? 'jpg' : 'png'}`
  const bytes = new Uint8Array(await response.arrayBuffer())
  let binary = ''
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return { ok: true, base64: btoa(binary), contentType, filename }
}

function parseFilename(disposition: string | null): string | undefined {
  if (!disposition) return
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) return decodeURIComponent(encoded.replace(/^"|"$/g, ''))
  return disposition.match(/filename="?([^";]+)"?/i)?.[1]
}
