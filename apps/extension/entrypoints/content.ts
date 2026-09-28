import { LocalServiceClient } from '../src/local-service/client'
import { CAPTURE_EVENT } from '../src/platform/boss/capture'
import { isCapturedJob } from '../src/platform/boss/messages'

export default defineContentScript({
  matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
  runAt: 'document_start',
  async main() {
    const client = new LocalServiceClient()
    const health = await client.health().catch(() => null)

    document.documentElement.dataset.jobSearchAssistant = health?.status ?? 'offline'

    document.addEventListener(CAPTURE_EVENT, (event) => {
      const detail = (event as CustomEvent<unknown>).detail
      if (!isCapturedJob(detail)) return

      void client.captureJobs({ jobs: [detail] }).catch((error: unknown) => {
        console.warn('[Job Search Assistant] failed to persist captured job', error)
      })
    })

    await injectScript('/boss.js', { keepInDom: true })
  },
})
