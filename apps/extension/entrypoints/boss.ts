import {
  CAPTURE_DIAGNOSTIC_EVENT,
  CAPTURE_DIAGNOSTIC_RESOLVED_EVENT,
  CAPTURE_EVENT,
  captureBossJob,
  diagnoseBossJobCapture,
} from '../src/platform/boss/capture'

export default defineUnlistedScript(() => {
  let lastFingerprint = ''
  let lastDiagnosticFingerprint = ''
  let timer: ReturnType<typeof setTimeout> | undefined

  const scheduleCapture = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      const job = captureBossJob(document, location)
      const diagnostic = diagnoseBossJobCapture(document, location)
      const missingFields = Array.isArray(diagnostic.details.missingFields)
        ? diagnostic.details.missingFields
        : []
      if (!job || missingFields.length) {
        const diagnosticFingerprint = JSON.stringify(diagnostic)
        if (diagnosticFingerprint !== lastDiagnosticFingerprint) {
          lastDiagnosticFingerprint = diagnosticFingerprint
          document.dispatchEvent(new CustomEvent(CAPTURE_DIAGNOSTIC_EVENT, {
            detail: diagnostic,
          }))
        }
        if (!job) return
      }
      else if (lastDiagnosticFingerprint) {
        document.dispatchEvent(new CustomEvent(CAPTURE_DIAGNOSTIC_RESOLVED_EVENT, {
          detail: { code: 'capture-incomplete' },
        }))
        lastDiagnosticFingerprint = ''
      }

      const fingerprint = `${job.platformJobId}:${job.description}`
      if (fingerprint === lastFingerprint) return
      lastFingerprint = fingerprint
      document.dispatchEvent(new CustomEvent(CAPTURE_EVENT, { detail: job }))
    }, 300)
  }

  new MutationObserver(scheduleCapture).observe(document.documentElement, {
    childList: true,
    subtree: true,
  })
  window.addEventListener('popstate', scheduleCapture)
  scheduleCapture()
})
