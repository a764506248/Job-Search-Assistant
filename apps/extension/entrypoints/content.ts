import {
  findBossChatImageInput,
  loadDefaultImage,
  mountResumeImageTestPanel,
  putFileIntoInput,
} from '../src/features/resume-image-test/panel'
import type { BrowserActionEnvelope, BrowserActionResult } from '../src/automation/protocol'
import { captureBossJob } from '../src/platform/boss/capture'
import {
  chatJobTitleMatches,
  fillChatEditor,
  findChatEditor,
  findSendButton,
  outgoingTextObserved,
  readChatIdentity,
} from '../src/platform/boss/chat'

export default defineContentScript({
  matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
  runAt: 'document_idle',
  async main() {
    // 0.2.0 image-test mode: deliberately do not inject boss.js and do not start
    // the original capture/analyse/sync pipeline.
    mountResumeImageTestPanel(document)
    browser.runtime.onMessage.addListener((message: unknown) => {
      if (!isBrowserActionMessage(message)) return
      return handleBrowserAction(message.envelope)
    })
  },
})

function isBrowserActionMessage(
  message: unknown,
): message is { type: 'job-search-assistant:browser-action'; envelope: BrowserActionEnvelope } {
  return !!message && typeof message === 'object'
    && (message as { type?: unknown }).type === 'job-search-assistant:browser-action'
    && !!(message as { envelope?: unknown }).envelope
}

async function handleBrowserAction(
  envelope: BrowserActionEnvelope,
): Promise<Omit<BrowserActionResult, 'requestId'>> {
  if (envelope.action === 'session_status') {
    return {
      status: 'success',
      evidence: {
        url: location.href,
        bossDomain: /(^|\.)zhipin\.com$/.test(location.hostname),
        documentReady: document.readyState === 'complete',
      },
    }
  }
  if (envelope.action === 'capture_job') {
    const job = captureBossJob(document, location)
    return job
      ? { status: 'success', evidence: { job } }
      : { status: 'blocked', evidence: {}, error: '当前页面没有可完整识别的岗位' }
  }
  if (envelope.action === 'validate_identity') {
    const chatIdentity = readChatIdentity(document)
    const job = captureBossJob(document, location)
    const expectedJobId = String(envelope.payload.expectedJobId ?? '')
    const expectedTitle = String(envelope.payload.expectedTitle ?? '')
    const requireChat = envelope.payload.requireChat === true
    const chatMatched = chatJobTitleMatches(chatIdentity, expectedTitle)
    const identityMatched = chatMatched
      || (!requireChat && !!job
        && (!expectedJobId || job.platformJobId === expectedJobId)
        && sameJobTitle(job.title, expectedTitle))
    return {
      status: identityMatched ? 'success' : 'blocked',
      evidence: {
        identityMatched,
        actualTitle: chatIdentity?.title ?? job?.title,
        actualCompany: chatIdentity?.companyName ?? job?.companyName,
      },
      error: identityMatched
        ? undefined
        : requireChat
          ? '尚未进入目标岗位聊天页'
          : '当前岗位与任务目标不一致，已停止操作',
    }
  }
  if (envelope.action === 'open_chat') {
    const expectedTitle = String(envelope.payload.expectedTitle ?? '')
    const expectedJobId = String(envelope.payload.expectedJobId ?? '')
    const job = await waitForExpectedJob(expectedJobId, expectedTitle)
    if (!job) {
      const actual = captureBossJob(document, location)
      return {
        status: 'blocked',
        evidence: {
          identityMatched: false,
          sideEffectExecuted: false,
          actualTitle: actual?.title,
          actualCompany: actual?.companyName,
          actualJobId: actual?.platformJobId,
        },
        error: '职位详情与任务目标不一致，未打开聊天',
      }
    }
    const button = Array.from(document.querySelectorAll<HTMLElement>('button,a'))
      .find(item => ['立即沟通', '继续沟通'].includes(item.textContent?.trim() ?? ''))
    if (!button) {
      return {
        status: 'blocked',
        evidence: { identityMatched: true, sideEffectExecuted: false },
        error: '未找到明确的沟通入口',
      }
    }
    button.click()
    await new Promise(resolve => setTimeout(resolve, 1200))
    const chatIdentity = readChatIdentity(document)
    const chatMatched = chatJobTitleMatches(chatIdentity, expectedTitle)
    return chatMatched
      ? { status: 'success', evidence: { identityMatched: true, chatOpened: true } }
      : {
          status: 'blocked',
          evidence: { identityMatched: true, chatOpened: false },
          error: '已点击沟通入口，但聊天身份未通过二次校验',
        }
  }
  if (envelope.action === 'send_greeting') {
    return sendGreetingWithConfirmation(envelope)
  }
  if (envelope.action === 'send_resume') {
    return sendResumeWithPreview(envelope)
  }
  return {
    status: 'blocked',
    evidence: { sideEffectExecuted: false },
    error: `动作 ${envelope.action} 尚未在安全执行器中启用`,
  }
}

async function waitForExpectedJob(expectedJobId: string, expectedTitle: string) {
  const deadline = Date.now() + 12_000
  while (Date.now() < deadline) {
    const job = captureBossJob(document, location)
    if (job
      && (!expectedJobId || job.platformJobId === expectedJobId)
      && sameJobTitle(job.title, expectedTitle)) return job
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  return null
}

function sameJobTitle(actual: string, expected: string): boolean {
  return actual.replace(/\s+/g, '').toLowerCase() === expected.replace(/\s+/g, '').toLowerCase()
}

async function sendResumeWithPreview(
  envelope: BrowserActionEnvelope,
): Promise<Omit<BrowserActionResult, 'requestId'>> {
  const expectedTitle = String(envelope.payload.expectedTitle ?? '')
  const expectedCompany = String(envelope.payload.expectedCompany ?? '')
  const identity = readChatIdentity(document)
  if (!chatJobTitleMatches(identity, expectedTitle)) {
    return {
      status: 'blocked',
      evidence: { identityMatched: false, sideEffectExecuted: false },
      error: '聊天页岗位或公司与任务目标不一致，已停止发送简历',
    }
  }
  const input = findBossChatImageInput(document)
  if (!input) {
    return {
      status: 'blocked',
      evidence: { identityMatched: true, sideEffectExecuted: false },
      error: '未找到 BOSS 聊天图片上传控件',
    }
  }
  const { file, url } = await loadDefaultImage()
  const confirmed = await confirmResumePreview(file, url, expectedTitle, expectedCompany)
  URL.revokeObjectURL(url)
  if (!confirmed) {
    return {
      status: 'confirmation_required',
      evidence: { identityMatched: true, userConfirmed: false, sideEffectExecuted: false },
      error: '用户取消发送简历',
    }
  }
  const outgoingImagesBefore = countOutgoingImages(document)
  putFileIntoInput(input, file)
  await new Promise(resolve => setTimeout(resolve, 1500))
  const imageMessageObserved = countOutgoingImages(document) > outgoingImagesBefore
  const evidence = {
    identityMatched: true,
    userConfirmed: true,
    sideEffectExecuted: true,
    imageMessageObserved,
    filename: file.name,
  }
  return imageMessageObserved
    ? { status: 'success', evidence }
    : {
        status: 'uncertain',
        evidence,
        error: '已注入简历图片，但未观察到新的图片消息；禁止自动重试',
      }
}

function countOutgoingImages(doc: Document): number {
  return doc.querySelectorAll([
    '.message-item.myself img',
    '.message-item.right img',
    '.chat-message.is-self img',
    '[class*="message"] [class*="self"] img',
  ].join(',')).length
}

function confirmResumePreview(
  file: File,
  url: string,
  title: string,
  company: string,
): Promise<boolean> {
  return new Promise((resolve) => {
    const host = document.createElement('div')
    host.id = 'job-search-assistant-confirm-resume'
    const shadow = host.attachShadow({ mode: 'open' })
    shadow.innerHTML = `<style>
      .backdrop{position:fixed;inset:0;z-index:2147483647;display:grid;place-items:center;background:rgba(8,20,16,.68);font:14px/1.5 system-ui,sans-serif}
      .card{width:min(420px,calc(100vw - 32px));padding:20px;border-radius:16px;background:white;color:#17251f;box-shadow:0 24px 80px rgba(0,0,0,.3)}
      h2{margin:0 0 8px;font-size:19px}p{margin:5px 0;color:#586a61}img{display:block;width:100%;max-height:340px;margin:14px 0;object-fit:contain;border:1px solid #dce8e2;border-radius:10px;background:#f7faf8}
      .actions{display:flex;gap:10px}.actions button{flex:1;padding:10px;border:0;border-radius:8px;font-weight:700;cursor:pointer}.cancel{background:#edf2ef}.confirm{background:#07825f;color:white}
    </style><section class="backdrop"><div class="card" role="dialog" aria-modal="true" aria-label="确认发送简历">
      <h2>确认发送简历图片</h2><p>岗位：${escapeHtml(title)}</p><p>公司：${escapeHtml(company)}</p><p>文件：${escapeHtml(file.name)}</p>
      <img alt="待发送简历图片预览"><div class="actions"><button class="cancel">取消</button><button class="confirm">确认发送</button></div>
    </div></section>`
    shadow.querySelector<HTMLImageElement>('img')!.src = url
    const finish = (confirmed: boolean) => { host.remove(); resolve(confirmed) }
    shadow.querySelector<HTMLButtonElement>('.cancel')!.addEventListener('click', () => finish(false))
    shadow.querySelector<HTMLButtonElement>('.confirm')!.addEventListener('click', () => finish(true))
    document.documentElement.append(host)
  })
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]!)
}

async function sendGreetingWithConfirmation(
  envelope: BrowserActionEnvelope,
): Promise<Omit<BrowserActionResult, 'requestId'>> {
  const expectedTitle = String(envelope.payload.expectedTitle ?? '')
  const expectedCompany = String(envelope.payload.expectedCompany ?? '')
  const text = String(envelope.payload.text ?? '').trim()
  const identity = readChatIdentity(document)
  if (!text || !chatJobTitleMatches(identity, expectedTitle)) {
    return {
      status: 'blocked',
      evidence: { identityMatched: false, sideEffectExecuted: false },
      error: '聊天页岗位或公司与任务目标不一致，已停止发送',
    }
  }
  const confirmed = window.confirm(
    `确认发送问候语？\n岗位：${expectedTitle}\n公司：${expectedCompany}\n\n${text}`,
  )
  if (!confirmed) {
    return {
      status: 'confirmation_required',
      evidence: { identityMatched: true, sideEffectExecuted: false },
      error: '用户取消发送',
    }
  }
  const editor = findChatEditor(document)
  const sendButton = findSendButton(document)
  if (!editor || !sendButton) {
    return {
      status: 'blocked',
      evidence: { identityMatched: true, sideEffectExecuted: false },
      error: '未找到唯一聊天编辑器或发送按钮',
    }
  }
  fillChatEditor(editor, text)
  sendButton.click()
  await new Promise(resolve => setTimeout(resolve, 800))
  const messageBubbleObserved = outgoingTextObserved(document, text)
  const editorCleared = editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement
    ? editor.value.trim() === ''
    : (editor.textContent ?? '').trim() === ''
  const evidence = {
    identityMatched: true,
    userConfirmed: true,
    sideEffectExecuted: true,
    messageBubbleObserved,
    editorCleared,
  }
  return messageBubbleObserved && editorCleared
    ? { status: 'success', evidence }
    : {
        status: 'uncertain',
        evidence,
        error: '已点击发送，但未同时观察到消息气泡和编辑器清空；禁止自动重试',
      }
}
