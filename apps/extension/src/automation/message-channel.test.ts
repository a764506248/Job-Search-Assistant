import { describe, expect, it } from 'vitest'

import { isClosedMessageChannel } from './message-channel'

describe('isClosedMessageChannel', () => {
  it('recognizes Chrome navigation channel closure errors', () => {
    expect(isClosedMessageChannel(new Error(
      'A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received',
    ))).toBe(true)
  })

  it('recognizes a content script that is still loading after navigation', () => {
    expect(isClosedMessageChannel('Could not establish connection. Receiving end does not exist.')).toBe(true)
  })

  it('does not hide unrelated extension failures', () => {
    expect(isClosedMessageChannel(new Error('permission denied'))).toBe(false)
  })
})
