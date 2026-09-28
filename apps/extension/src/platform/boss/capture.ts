import type { CapturedJob } from '@job-search-assistant/contracts'

export const CAPTURE_EVENT = '__job_search_assistant_boss_capture__'

const SELECTORS = {
  title: ['.job-detail-info .name h1', '.job-detail-box .name h1', '.job-detail-box .job-name', '.job-title'],
  company: ['.job-detail-company .company-name', '.company-info .company-name', '.job-detail-box .company-name'],
  description: ['.job-detail-section .job-sec-text', '.job-detail-box .job-sec-text', '.job-detail-content .job-sec-text', '.job-sec-text'],
  salary: ['.job-detail-info .salary', '.job-detail-box .salary'],
  location: ['.job-detail-info .text-desc', '.job-detail-box .location-address'],
  recruiterName: ['.boss-info-attr .name', '.job-boss-info .name'],
  recruiterTitle: ['.boss-info-attr .boss-info-label', '.job-boss-info .boss-title'],
  tags: ['.job-detail-info .tag-list li', '.job-detail-box .job-tags span'],
  skills: ['.job-detail-section .job-tags span', '.job-detail-box .job-tags span'],
} as const

function text(document: Document, selectors: readonly string[]): string | undefined {
  for (const selector of selectors) {
    const value = document.querySelector(selector)?.textContent?.trim()
    if (value) return value
  }
  return undefined
}

function texts(document: Document, selectors: readonly string[]): string[] {
  for (const selector of selectors) {
    const values = Array.from(document.querySelectorAll(selector))
      .map((node) => node.textContent?.trim() ?? '')
      .filter(Boolean)
    if (values.length) return [...new Set(values)]
  }
  return []
}

function platformJobId(document: Document, pathname: string): string | undefined {
  const match = pathname.match(/\/job_detail\/([^/.]+)(?:\.html)?/)
  if (match?.[1]) return match[1]

  const selected = document.querySelector<HTMLElement>(
    '[data-jobid].selected,[data-job-id].selected,.job-card-wrapper.active',
  )
  return selected?.dataset.jobid ?? selected?.dataset.jobId
}

export function captureBossJob(
  document: Document,
  page: Pick<Location, 'href' | 'pathname'>,
  capturedAt = new Date(),
): CapturedJob | null {
  const id = platformJobId(document, page.pathname)
  const title = text(document, SELECTORS.title)
  const companyName = text(document, SELECTORS.company)
  const description = text(document, SELECTORS.description)
  if (!id || !title || !companyName || !description) return null

  const labels = texts(document, SELECTORS.tags)
  return {
    platform: 'boss',
    platformJobId: id,
    url: page.href,
    title,
    companyName,
    location: text(document, SELECTORS.location),
    salaryText: text(document, SELECTORS.salary),
    experience: labels.find((label) => /经验|年/.test(label)),
    education: labels.find((label) => /学历|本科|专科|硕士|博士/.test(label)),
    description,
    skills: texts(document, SELECTORS.skills),
    recruiterName: text(document, SELECTORS.recruiterName),
    recruiterTitle: text(document, SELECTORS.recruiterTitle),
    capturedAt: capturedAt.toISOString(),
    source: 'dom',
  }
}
