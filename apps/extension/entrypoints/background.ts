export default defineBackground(() => {
  console.info('[Job Search Assistant] resume image test background ready')

  browser.runtime.onMessage.addListener((message: unknown) => {
    if (!isDefaultResumeImageRequest(message)) return
    return fetchDefaultResumeImage()
  })
})

interface DefaultResumeImageRequest {
  type: 'job-search-assistant:get-default-resume-image'
}

interface DefaultResumeImageResponse {
  ok: true
  base64: string
  contentType: string
  filename: string
}

function isDefaultResumeImageRequest(message: unknown): message is DefaultResumeImageRequest {
  return typeof message === 'object'
    && message !== null
    && (message as { type?: unknown }).type === 'job-search-assistant:get-default-resume-image'
}

async function fetchDefaultResumeImage(): Promise<DefaultResumeImageResponse> {
  const response = await fetch('http://127.0.0.1:8765/v1/resumes/default-image', {
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
