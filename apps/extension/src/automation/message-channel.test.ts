import { describe, expect, it } from 'vitest'

import { isClosedMessageChannel, isMissingMessageReceiver } from './message-channel'

describe('isClosedMessageChannel', () => {
  it('recognizes Chrome navigation channel closure errors', () => {
    expect(isClosedMessageChannel(new Error(
      'A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received',
    ))).toBe(true)
  })

  it('recognizes a content script that is still loading after navigation', () => {
    const error = 'Could not establish connection. Receiving end does not exist.'
    expect(isClosedMessageChannel(error)).toBe(true)
    expect(isMissingMessageReceiver(error)).toBe(true)
  })

  it('distinguishes a missing receiver from a channel closed after execution started', () => {
    expect(isMissingMessageReceiver(
      'A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received',
    )).toBe(false)
  })

  it('does not hide unrelated extension failures', () => {
    expect(isClosedMessageChannel(new Error('permission denied'))).toBe(false)
  })
})
