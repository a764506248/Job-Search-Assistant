import { LocalServiceClient } from '../src/local-service/client'
import { mountJobAnalysisPanel } from '../src/features/control/job-analysis-panel'
import {
  CAPTURE_DIAGNOSTIC_EVENT,
  CAPTURE_DIAGNOSTIC_RESOLVED_EVENT,
  CAPTURE_EVENT,
} from '../src/platform/boss/capture'
import { isCapturedJob, isCaptureDiagnostic } from '../src/platform/boss/messages'

export default defineContentScript({
  matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
  runAt: 'document_start',
  async main() {
    const client = new LocalServiceClient()
    const panel = mountJobAnalysisPanel(document)
    panel.showIdle('正在连接本地服务…')
    let serviceOnline = false
    let consecutiveHealthFailures = 0

    const reportClientEvent = (
      event: string,
      error: unknown,
      level: 'warning' | 'error',
      platformJobId?: string,
      details?: Record<string, unknown>,
    ) => {
      const message = error instanceof Error ? error.message : String(error)
      void client.logClientError({
        source: 'extension-content',
        level,
        event,
        message: message.slice(0, 2000),
        pageUrl: location.href.slice(0, 1000),
        platformJobId,
        details,
        occurredAt: new Date().toISOString(),
      }).catch((reportingError: unknown) => {
        console.warn('[Job Search Assistant] failed to report client error', reportingError)
      })
    }
    const reportError = (event: string, error: unknown, platformJobId?: string) => {
      reportClientEvent(event, error, 'error', platformJobId)
    }

    const refreshServiceConnection = async () => {
      const health = await client.health().catch(() => null)
      if (health) {
        const recovered = !serviceOnline && consecutiveHealthFailures > 0
        serviceOnline = true
        consecutiveHealthFailures = 0
        document.documentElement.dataset.jobSearchAssistant = health.status
        panel.clearDiagnostic('local-service-unavailable')
        panel.showIdle(recovered
          ? '本地服务已重新连接，正在等待当前职位信息…'
          : '本地服务已连接，正在等待当前职位信息…')
        return
      }
      serviceOnline = false
      consecutiveHealthFailures += 1
      document.documentElement.dataset.jobSearchAssistant = 'offline'
      panel.showIdle('本地服务暂时不可达，正在自动重连…')
      panel.reportDiagnostic({
        level: consecutiveHealthFailures >= 3 ? 'error' : 'warning',
        code: 'local-service-unavailable',
        message: `本地服务暂时不可达，正在自动重连（第 ${consecutiveHealthFailures} 次）`,
        details: { endpoint: 'http://127.0.0.1:8765/v1/health' },
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

    document.addEventListener(CAPTURE_DIAGNOSTIC_EVENT, (event) => {
      const detail = (event as CustomEvent<unknown>).detail
      if (isCaptureDiagnostic(detail)) {
        panel.reportDiagnostic(detail)
        if (serviceOnline) {
          reportClientEvent(detail.code, detail.message, detail.level, undefined, detail.details)
        }
      }
    })

    document.addEventListener(CAPTURE_DIAGNOSTIC_RESOLVED_EVENT, (event) => {
      const detail = (event as CustomEvent<{ code?: unknown }>).detail
      if (typeof detail?.code === 'string') panel.clearDiagnostic(detail.code)
    })

    await injectScript('/boss.js', { keepInDom: true })
    void refreshServiceConnection()
    window.setInterval(() => { void refreshServiceConnection() }, 10000)
  },
})
