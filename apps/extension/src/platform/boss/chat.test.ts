import { beforeEach, describe, expect, it } from 'vitest'
import {
  chatIdentityMatches,
  fillChatEditor,
  findChatEditor,
  findSendButton,
  outgoingTextObserved,
  readChatIdentity,
} from './chat'

describe('Boss chat safety helpers', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('requires exact normalized job and company identity', () => {
    document.body.innerHTML = '<header class="chat-header"><b class="job-name">AI Agent 工程师</b><span class="company-name">示例 科技</span></header>'
    const identity = readChatIdentity(document)
    expect(chatIdentityMatches(identity, 'AI Agent工程师', '示例科技')).toBe(true)
    expect(chatIdentityMatches(identity, '后端工程师', '示例科技')).toBe(false)
  })

  it('fills only a recognized editor and finds an exact send button', () => {
    document.body.innerHTML = '<div class="chat-editor"><div contenteditable="true"></div></div><button>发送</button><button>发送简历</button>'
    const editor = findChatEditor(document)!
    fillChatEditor(editor, '您好，期待沟通')
    expect(editor.textContent).toBe('您好，期待沟通')
    expect(findSendButton(document)?.textContent).toBe('发送')
  })

  it('observes text only in an outgoing message bubble', () => {
    document.body.innerHTML = '<div class="message-item myself">您好，期待沟通</div><div class="message-item">其他消息</div>'
    expect(outgoingTextObserved(document, '您好，期待沟通')).toBe(true)
    expect(outgoingTextObserved(document, '不存在')).toBe(false)
  })
})
