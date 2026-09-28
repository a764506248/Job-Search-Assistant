import { LocalServiceClient } from '../src/local-service/client'
import type { CapturedJob } from '@job-search-assistant/contracts'

const CAPTURE_EVENT = '__job_search_assistant_boss_capture__'

function isCapturedJob(value: unknown): value is CapturedJob {
  if (!value || typeof value !== 'object') return false
  const job = value as Partial<CapturedJob>
  return (
    job.platform === 'boss' &&
    typeof job.platformJobId === 'string' &&
    typeof job.url === 'string' &&
    typeof job.title === 'string' &&
    typeof job.companyName === 'string' &&
    typeof job.description === 'string' &&
    Array.isArray(job.skills)
  )
}

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
