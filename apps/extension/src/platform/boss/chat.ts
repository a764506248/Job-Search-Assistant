export interface ChatIdentity {
  title: string
  companyName?: string
}

const TITLE_SELECTORS = [
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

export function findChatEditor(doc: Document): HTMLElement | null {
  for (const selector of EDITOR_SELECTORS) {
    const editor = doc.querySelector<HTMLElement>(selector)
    if (editor) return editor
  }
  return null
}

export function fillChatEditor(editor: HTMLElement, text: string): void {
  if (editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement) {
    editor.value = text
  }
  else {
    editor.textContent = text
  }
  editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }))
}

export function findSendButton(doc: Document): HTMLButtonElement | null {
  return Array.from(doc.querySelectorAll<HTMLButtonElement>('button'))
    .find(button => button.textContent?.trim() === '发送' && !button.disabled) ?? null
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
