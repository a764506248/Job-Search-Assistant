import type { CapturedJob } from '@job-search-assistant/contracts'

const CAPTURE_EVENT = '__job_search_assistant_boss_capture__'
const SELECTORS = {
  title: [
    '.job-detail-info .name h1',
    '.job-detail-box .name h1',
    '.job-detail-box .job-name',
    '.job-title',
  ],
  company: [
    '.job-detail-company .company-name',
    '.company-info .company-name',
    '.job-detail-box .company-name',
  ],
  description: [
    '.job-detail-section .job-sec-text',
    '.job-detail-box .job-sec-text',
    '.job-detail-content .job-sec-text',
    '.job-sec-text',
  ],
  salary: ['.job-detail-info .salary', '.job-detail-box .salary'],
  location: ['.job-detail-info .text-desc', '.job-detail-box .location-address'],
  recruiterName: ['.boss-info-attr .name', '.job-boss-info .name'],
  recruiterTitle: ['.boss-info-attr .boss-info-label', '.job-boss-info .boss-title'],
  tags: ['.job-detail-info .tag-list li', '.job-detail-box .job-tags span'],
  skills: ['.job-detail-section .job-tags span', '.job-detail-box .job-tags span'],
} as const

function text(selector: readonly string[]): string | undefined {
  for (const item of selector) {
    const value = document.querySelector<HTMLElement>(item)?.innerText.trim()
    if (value) return value
  }
  return undefined
}

function texts(selector: readonly string[]): string[] {
  for (const item of selector) {
    const values = Array.from(document.querySelectorAll<HTMLElement>(item))
      .map((node) => node.innerText.trim())
      .filter(Boolean)
    if (values.length) return [...new Set(values)]
  }
  return []
}

function platformJobId(): string | undefined {
  const match = location.pathname.match(/\/job_detail\/([^/.]+)(?:\.html)?/)
  if (match?.[1]) return match[1]

  const selected = document.querySelector<HTMLElement>(
    '[data-jobid].selected,[data-job-id].selected,.job-card-wrapper.active',
  )
  return selected?.dataset.jobid ?? selected?.dataset.jobId
}

function classifyLabels(labels: string[]) {
  return {
    experience: labels.find((label) => /经验|年/.test(label)),
    education: labels.find((label) => /学历|本科|专科|硕士|博士/.test(label)),
  }
}

function capture(): CapturedJob | null {
  const id = platformJobId()
  const title = text(SELECTORS.title)
  const companyName = text(SELECTORS.company)
  const description = text(SELECTORS.description)
  if (!id || !title || !companyName || !description) return null

  const labels = texts(SELECTORS.tags)
  const { experience, education } = classifyLabels(labels)
  return {
    platform: 'boss',
    platformJobId: id,
    url: location.href,
    title,
    companyName,
    location: text(SELECTORS.location),
    salaryText: text(SELECTORS.salary),
    experience,
    education,
    description,
    skills: texts(SELECTORS.skills),
    recruiterName: text(SELECTORS.recruiterName),
    recruiterTitle: text(SELECTORS.recruiterTitle),
    capturedAt: new Date().toISOString(),
    source: 'dom',
  }
}

export default defineUnlistedScript(() => {
  let lastFingerprint = ''
  let timer: ReturnType<typeof setTimeout> | undefined

  const scheduleCapture = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      const job = capture()
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
