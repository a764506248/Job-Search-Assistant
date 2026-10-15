import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  findBossChatImageInput,
  readAutomationSettings,
} from './panel'

describe('resume image utilities', () => {
  const storage: Record<string, unknown> = {}
  beforeEach(() => {
    for (const key of Object.keys(storage)) delete storage[key]
    vi.stubGlobal('browser', {
      storage: {
        local: {
          get: vi.fn(async (key: string) => ({ [key]: storage[key] })),
        },
      },
    })
  })
  afterEach(() => {
    document.documentElement.innerHTML = '<head></head><body></body>'
    vi.unstubAllGlobals()
  })

  it('selects the chat image input instead of resume-library inputs', () => {
    document.body.innerHTML = `
      <input type="file" accept=".pdf,.doc" ka="user-resume-upload-file">
      <input id="chat-image" type="file" accept="image/gif,image/jpeg,image/png">
      <input type="file" accept="image/png" ka="user-resume-upload-file">`
    expect(findBossChatImageInput(document)?.id).toBe('chat-image')
  })

  it('defaults to automatic and preserves legacy resume-send preferences', async () => {
    expect(await readAutomationSettings()).toMatchObject({ resumeSendMode: 'automatic' })
    storage.jobSearchAssistantAutomationSettings = { resumeSendMode: 'off', collapsed: true }
    expect(await readAutomationSettings()).toMatchObject({ resumeSendMode: 'off' })
  })
})
