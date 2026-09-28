import { LocalServiceClient } from '../src/local-service/client'
import { mountJobAnalysisPanel } from '../src/features/control/job-analysis-panel'
import { CAPTURE_EVENT } from '../src/platform/boss/capture'
import { isCapturedJob } from '../src/platform/boss/messages'

export default defineContentScript({
  matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
  runAt: 'document_start',
  async main() {
    const client = new LocalServiceClient()
    const panel = mountJobAnalysisPanel(document)
    panel.showIdle('正在连接本地服务…')
    const health = await client.health().catch(() => null)

    document.documentElement.dataset.jobSearchAssistant = health?.status ?? 'offline'
    if (!health) panel.showIdle('本地服务未启动，请先运行 Docker 服务。')

    const reportError = (event: string, error: unknown, platformJobId?: string) => {
      const message = error instanceof Error ? error.message : String(error)
      void client.logClientError({
        source: 'extension-content',
        level: 'error',
        event,
        message: message.slice(0, 2000),
        pageUrl: location.href.slice(0, 1000),
        platformJobId,
        occurredAt: new Date().toISOString(),
      }).catch((reportingError: unknown) => {
        console.warn('[Job Search Assistant] failed to report client error', reportingError)
      })
    }

    document.addEventListener(CAPTURE_EVENT, (event) => {
      const detail = (event as CustomEvent<unknown>).detail
      if (!isCapturedJob(detail)) return

      panel.showLoading(detail)
      void Promise.all([
        client.captureJobs({ jobs: [detail] }),
        client.matchJob({ title: detail.title, jobText: detail.description, skills: detail.skills }),
      ]).then(([, result]) => panel.showResult(detail, result)).catch((error: unknown) => {
        console.warn('[Job Search Assistant] failed to analyze captured job', error)
        reportError('job-analysis-failed', error, detail.platformJobId)
        panel.showError(detail, '分析失败，请确认本地服务和向量模型已经启动。')
      })
    })

    await injectScript('/boss.js', { keepInDom: true })
  },
})
