const GET_IMAGE_MESSAGE = 'job-search-assistant:get-default-resume-image'
const SETTINGS_KEY = 'jobSearchAssistantAutomationSettings'

interface ImageResponse {
  ok: true
  base64: string
  contentType: string
  filename: string
}

export type ResumeSendMode = 'automatic' | 'confirm' | 'off'

export interface AutomationSettings {
  resumeSendMode: ResumeSendMode
}

const DEFAULT_SETTINGS: AutomationSettings = {
  resumeSendMode: 'automatic',
}

export async function readAutomationSettings(): Promise<AutomationSettings> {
  const stored = await browser.storage.local.get(SETTINGS_KEY)
  const value = stored[SETTINGS_KEY] as Partial<AutomationSettings> | undefined
  return {
    resumeSendMode: ['automatic', 'confirm', 'off'].includes(value?.resumeSendMode ?? '')
      ? value!.resumeSendMode as ResumeSendMode
      : DEFAULT_SETTINGS.resumeSendMode,
  }
}

export function findBossChatImageInput(doc: Document): HTMLInputElement | null {
  const inputs = Array.from(doc.querySelectorAll<HTMLInputElement>('input[type="file"]'))
  return inputs.find((input) => {
    const accept = input.accept.toLowerCase()
    const marker = `${input.id} ${input.name} ${input.getAttribute('ka') ?? ''}`.toLowerCase()
    return accept.includes('image') && !marker.includes('resume-upload')
  }) ?? null
}

export function putFileIntoInput(input: HTMLInputElement, file: File): void {
  const transfer = new DataTransfer()
  transfer.items.add(file)
  input.files = transfer.files
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

export async function loadDefaultImage(): Promise<{ file: File; url: string }> {
  const response = await browser.runtime.sendMessage({ type: GET_IMAGE_MESSAGE }) as ImageResponse
  if (!response?.ok || !response.base64) throw new Error('扩展后台没有返回默认简历图片')
  const binary = atob(response.base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  const file = new File([bytes], response.filename, { type: response.contentType })
  return { file, url: URL.createObjectURL(file) }
}
