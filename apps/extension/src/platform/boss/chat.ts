export interface ChatIdentity {
  title: string
  companyName?: string
}

export interface ChatContextMatch {
  matched: boolean
  mode: 'chat_page' | 'inline_dialog' | 'none'
  actualTitle?: string
  actualCompany?: string
}

interface InlineJobIdentity {
  platformJobId: string
  title: string
  companyName?: string
}

const TITLE_SELECTORS = [
  '.chat-position-content .position-main .position-name',
  '.chat-position-content .position-name',
  '.chat-position-bar .bar-position-name',
  '.bar-position-name',
  '.chat-info .job-name',
  '.chat-header .job-name',
  '.chat-conversation .job-name',
  '[class*="chat"] [class*="job-name"]',
]

const COMPANY_SELECTORS = [
  '.chat-info .company-name',
  '.chat-header .company-name',
  '.chat-conversation .company-name',
  '[class*="chat"] [class*="company-name"]',
]

const EDITOR_SELECTORS = [
  '.chat-editor [contenteditable="true"]',
  '.message-editor [contenteditable="true"]',
  'textarea[placeholder*="简短描述"]',
  'textarea[placeholder*="消息"]',
  '[class*="chat"] textarea',
  '[contenteditable="true"][role="textbox"]',
]

export function readChatIdentity(doc: Document): ChatIdentity | null {
  const title = firstText(doc, TITLE_SELECTORS)
  const companyName = firstText(doc, COMPANY_SELECTORS)
  return title ? { title, companyName: companyName || undefined } : null
}

export function chatJobTitleMatches(
  identity: ChatIdentity | null,
  expectedTitle: string,
): boolean {
  return !!identity
    && normalize(identity.title) === normalize(expectedTitle)
}

export function matchChatContext(
  doc: Document,
  expectedJobId: string,
  expectedTitle: string,
  inlineJob: InlineJobIdentity | null,
): ChatContextMatch {
  const chatIdentity = readChatIdentity(doc)
  if (chatIdentity) {
    return {
      matched: chatJobTitleMatches(chatIdentity, expectedTitle),
      mode: 'chat_page',
      actualTitle: chatIdentity.title,
      actualCompany: chatIdentity.companyName,
    }
  }

  const editor = findChatEditor(doc)
  const matched = !!editor
    && !!inlineJob
    && (!expectedJobId || inlineJob.platformJobId === expectedJobId)
    && normalize(inlineJob.title) === normalize(expectedTitle)
  return {
    matched,
    mode: editor ? 'inline_dialog' : 'none',
    actualTitle: inlineJob?.title,
    actualCompany: inlineJob?.companyName,
  }
}

export function findChatEditor(doc: Document): HTMLElement | null {
  for (const selector of EDITOR_SELECTORS) {
    const editor = Array.from(doc.querySelectorAll<HTMLElement>(selector))
      .find(candidate => isUsableElement(candidate))
    if (editor) return editor
  }
  return null
}

export function fillChatEditor(editor: HTMLElement, text: string): void {
  editor.focus()
  if (editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement) {
    const prototype = editor instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype
    const valueSetter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
    valueSetter?.call(editor, text)
  }
  else {
    editor.textContent = text
  }
  editor.dispatchEvent(new InputEvent('beforeinput', {
    bubbles: true,
    cancelable: true,
    inputType: 'insertText',
    data: text,
  }))
  editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }))
  editor.dispatchEvent(new Event('change', { bubbles: true }))
}

export function findSendButton(doc: Document, editor = findChatEditor(doc)): HTMLElement | null {
  const candidates = Array.from(doc.querySelectorAll<HTMLElement>([
    'button',
    '[role="button"]',
    '[class*="send"]',
  ].join(',')))
    .filter(candidate => candidate.textContent?.trim() === '发送')
    .filter(candidate => isUsableElement(candidate) && !isDisabled(candidate))

  if (!editor) return candidates[0] ?? null

  const ancestors: HTMLElement[] = []
  let ancestor = editor.parentElement
  while (ancestor && ancestors.length < 6) {
    ancestors.push(ancestor)
    ancestor = ancestor.parentElement
  }
  for (const container of ancestors) {
    const nearby = candidates.find(candidate => container.contains(candidate))
    if (nearby) return nearby
  }
  return candidates[0] ?? null
}

export function outgoingTextObserved(doc: Document, text: string): boolean {
  const candidates = doc.querySelectorAll<HTMLElement>([
    '.message-item.myself',
    '.message-item.right',
    '.chat-message.is-self',
    '[class*="message"] [class*="self"]',
  ].join(','))
  return Array.from(candidates).some(node => node.textContent?.includes(text))
}

function firstText(doc: Document, selectors: string[]): string {
  for (const selector of selectors) {
    const value = doc.querySelector(selector)?.textContent?.trim()
    if (value) return value
  }
  return ''
}

function normalize(value: string): string {
  return value.replace(/\s+/g, '').toLowerCase()
}

function isUsableElement(element: HTMLElement): boolean {
  if (element.hidden || element.getAttribute('aria-hidden') === 'true') return false
  const style = element.ownerDocument.defaultView?.getComputedStyle(element)
  return style?.display !== 'none'
    && style?.visibility !== 'hidden'
    && style?.pointerEvents !== 'none'
}

function isDisabled(element: HTMLElement): boolean {
  return (element instanceof HTMLButtonElement && element.disabled)
    || element.getAttribute('aria-disabled') === 'true'
    || element.hasAttribute('disabled')
}
