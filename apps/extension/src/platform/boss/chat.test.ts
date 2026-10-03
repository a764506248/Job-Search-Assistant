import { beforeEach, describe, expect, it } from 'vitest'
import {
  chatJobTitleMatches,
  fillChatEditor,
  findChatEditor,
  findSendButton,
  matchChatContext,
  outgoingTextObserved,
  readChatIdentity,
} from './chat'

describe('Boss chat safety helpers', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('requires the normalized job title but does not compare company names', () => {
    document.body.innerHTML = '<header class="chat-header"><b class="job-name">AI Agent 工程师</b><span class="company-name">示例 科技</span></header>'
    const identity = readChatIdentity(document)
    expect(chatJobTitleMatches(identity, 'AI Agent工程师')).toBe(true)
    expect(chatJobTitleMatches(identity, '后端工程师')).toBe(false)
  })

  it('can validate a chat title when the company field is absent', () => {
    document.body.innerHTML = '<header class="chat-header"><b class="job-name">AI Agent 工程师</b></header>'
    expect(chatJobTitleMatches(readChatIdentity(document), 'AI Agent工程师')).toBe(true)
  })

  it('reads the current BOSS v5550 conversation position', () => {
    document.body.innerHTML = '<div class="chat-position-content"><div class="position-main"><div class="position-content"><span class="position-name">AI Agent策略工程师（剧情与分镜方向）</span></div></div></div>'
    expect(readChatIdentity(document)?.title).toBe('AI Agent策略工程师（剧情与分镜方向）')
  })

  it('accepts an inline chat dialog when the verified job behind it still matches', () => {
    document.body.innerHTML = '<section class="boss-dialog"><textarea placeholder="请简短描述您的问题"></textarea><button disabled>发送</button></section>'
    expect(matchChatContext(document, 'job-42', 'AI Agent 工程师', {
      platformJobId: 'job-42',
      title: 'AI Agent工程师',
      companyName: '示例科技',
    })).toMatchObject({
      matched: true,
      mode: 'inline_dialog',
      actualTitle: 'AI Agent工程师',
    })
  })

  it('rejects an inline dialog when the underlying job id differs', () => {
    document.body.innerHTML = '<section class="boss-dialog"><textarea placeholder="请简短描述您的问题"></textarea></section>'
    expect(matchChatContext(document, 'expected-job', 'AI Agent 工程师', {
      platformJobId: 'other-job',
      title: 'AI Agent 工程师',
    }).matched).toBe(false)
  })

  it('does not fall back to the detail page when an explicit chat title mismatches', () => {
    document.body.innerHTML = '<header class="chat-header"><b class="job-name">后端工程师</b></header><div class="chat-editor"><textarea></textarea></div>'
    expect(matchChatContext(document, 'job-42', 'AI Agent 工程师', {
      platformJobId: 'job-42',
      title: 'AI Agent 工程师',
    })).toMatchObject({ matched: false, mode: 'chat_page', actualTitle: '后端工程师' })
  })

  it('fills only a recognized editor and finds an exact send button', () => {
    document.body.innerHTML = '<div class="chat-editor"><div contenteditable="true"></div></div><button>发送</button><button>发送简历</button>'
    const editor = findChatEditor(document)!
    fillChatEditor(editor, '您好，期待沟通')
    expect(editor.textContent).toBe('您好，期待沟通')
    expect(findSendButton(document)?.textContent).toBe('发送')
  })

  it('uses the native textarea setter so controlled editors receive input events', () => {
    document.body.innerHTML = '<section class="chat-editor"><textarea placeholder="消息"></textarea><button>发送</button></section>'
    const editor = findChatEditor(document) as HTMLTextAreaElement
    const inputEvents: string[] = []
    editor.addEventListener('beforeinput', () => inputEvents.push('beforeinput'))
    editor.addEventListener('input', () => inputEvents.push('input'))
    editor.addEventListener('change', () => inputEvents.push('change'))

    fillChatEditor(editor, '您好，期待沟通')

    expect(editor.value).toBe('您好，期待沟通')
    expect(inputEvents).toEqual(['beforeinput', 'input', 'change'])
  })

  it('ignores hidden and disabled duplicates and prefers the send control near the editor', () => {
    document.body.innerHTML = `
      <button style="display:none">发送</button>
      <button disabled>发送</button>
      <section class="chat-editor">
        <textarea placeholder="消息"></textarea>
        <div class="btn-send" role="button">发送</div>
      </section>
      <footer><button>发送</button></footer>
    `
    const editor = findChatEditor(document)!
    expect(findSendButton(document, editor)?.className).toBe('btn-send')
  })

  it('observes text only in an outgoing message bubble', () => {
    document.body.innerHTML = '<div class="message-item myself">您好，期待沟通</div><div class="message-item">其他消息</div>'
    expect(outgoingTextObserved(document, '您好，期待沟通')).toBe(true)
    expect(outgoingTextObserved(document, '不存在')).toBe(false)
  })
})
