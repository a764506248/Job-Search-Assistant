import { CAPTURE_EVENT, captureBossJob } from '../src/platform/boss/capture'

export default defineUnlistedScript(() => {
  let lastFingerprint = ''
  let timer: ReturnType<typeof setTimeout> | undefined

  const scheduleCapture = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      const job = captureBossJob(document, location)
      if (!job) return

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
