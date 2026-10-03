import type { CapturedJob } from '@job-search-assistant/contracts'
import { decodeBossSalaryText } from './salary'

export const CAPTURE_EVENT = '__job_search_assistant_boss_capture__'
export const CAPTURE_DIAGNOSTIC_EVENT = '__job_search_assistant_boss_capture_diagnostic__'
export const CAPTURE_DIAGNOSTIC_RESOLVED_EVENT = '__job_search_assistant_boss_capture_diagnostic_resolved__'

export interface CaptureDiagnostic {
  level: 'warning' | 'error'
  code: string
  message: string
  details: Record<string, unknown>
}

const SELECTORS = {
  title: ['.job-detail-info .job-name', '.job-detail-info .name h1', '.job-detail-box .name h1', '.job-detail-box .name', '.job-detail-box .job-name', 'h1.job-title', '.job-title .job-name', '.job-banner h1', '.job-primary h1'],
  company: [
    '.job-detail-company .company-name',
    '.company-info .company-name',
    '.job-detail-box .company-name',
    '.job-detail-company a[href*="/gongsi/"]',
    '.company-info a[href*="/gongsi/"]',
    '.job-detail-box .boss-info .company-name',
    '.job-detail-box .boss-info a[href*="/gongsi/"]',
    '.boss-info .company-name',
    '.boss-info a[href*="/gongsi/"]',
    'a.boss-info[href*="/gongsi/"]',
    '.company-info',
  ],
  companySize: ['.job-detail-company .company-scale', '.company-info .company-scale', '.company-info .company-tag-list li', '.company-info .company-info-item'],
  description: [
    '.job-detail-body .desc',
    '.job-detail-section .job-sec-text',
    '.job-detail-box .job-sec-text',
    '.job-detail-content .job-sec-text',
    '.job-sec-text',
  ],
  salary: ['.job-detail-info .salary', '.job-detail-box .salary', '.job-banner .salary', '.info-primary .salary'],
  location: ['.job-banner .text-city', '.info-primary .text-city', '.job-detail-header ul a', '.job-detail-info .text-city', '.job-detail-info .text-desc'],
  workAddress: ['.job-location .location-address', '.job-detail-box .location-address', '.location-address', '[class*="location-address"]'],
  recruiterName: ['.boss-info-attr .name', '.job-boss-info .name'],
  recruiterTitle: ['.boss-info-attr .boss-info-label', '.job-boss-info .boss-title'],
  tags: ['.job-detail-info .tag-list li', '.job-detail-header ul li', '.job-detail-box .job-tags span', '.job-banner .info-primary p .text-desc', '.info-primary p .text-desc'],
  skills: ['.job-detail-section .job-tags span', '.job-detail-box .job-tags span'],
} as const

const ACTIVE_CARD_SELECTOR = [
  '.job-card-wrapper.active', '.job-card-wrapper.selected',
  '.job-card-wrap.active', '.job-card-wrap.selected',
  '.job-list-item.active', '.job-list-item.selected',
  '.job-card-wrapper[aria-selected="true"]', '.job-card-wrap[aria-selected="true"]',
].join(',')

const CARD_SELECTOR = [
  '.job-card-wrapper', '.job-card-wrap', '.job-list-item', '.job-card-box',
].join(',')

const SALARY_PATTERN = /(?:\d{1,3}(?:\.\d+)?\s*[-–—~]\s*\d{1,3}(?:\.\d+)?K|\d{1,3}K以上)(?:[·・]\d{1,2}薪)?/i
const EXPERIENCE_PATTERN = /(?:经验不限|不限|在校生|应届生|\d{1,2}\s*[-–—~]\s*\d{1,2}年|\d{1,2}年以上)/
const EDUCATION_PATTERN = /(?:学历不限|不限|中专|高中|大专|专科|本科|硕士|博士)/
const LOCATION_PATTERN = /^(?:北京|上海|天津|重庆|深圳|广州|杭州|成都|武汉|西安|南京|苏州|长沙|郑州|青岛|厦门|合肥|福州|济南|东莞|佛山|无锡|宁波|珠海)(?:[·・][^\s]+)?$/
const COMPANY_SIZE_PATTERN = /(?:少于\s*\d+人|\d+\s*[-–—~]\s*\d+人|\d+人以上)/

function text(document: Document, selectors: readonly string[]): string | undefined {
  for (const selector of selectors) {
    const value = visibleNodeText(document.querySelector(selector))
    if (value) return value
  }
  return undefined
}

function texts(document: Document, selectors: readonly string[]): string[] {
  for (const selector of selectors) {
    const values = Array.from(document.querySelectorAll(selector))
      .map(visibleNodeText)
      .filter(Boolean)
    if (values.length) return [...new Set(values)]
  }
  return []
}

function visibleNodeText(node: Element | null | undefined): string {
  if (!node) return ''
  const hiddenFragments = Array.from(node.querySelectorAll<HTMLElement>(
    'script,noscript,template,[hidden],[aria-hidden="true"]',
  )).map(item => item.textContent?.trim() ?? '').filter(Boolean)
  let rendered = node instanceof HTMLElement ? node.innerText?.trim() : ''
  for (const fragment of hiddenFragments) rendered = rendered.replace(fragment, '').trim()
  if (rendered) return rendered
  // jsdom has no layout-backed innerText. Removing non-visible content keeps
  // fixtures representative and prevents style/script text from becoming JD.
  const clone = node.cloneNode(true) as Element
  clone.querySelectorAll('style,script,noscript,template,[hidden],[aria-hidden="true"]')
    .forEach(item => item.remove())
  return clone.textContent?.trim() ?? ''
}

function platformJobId(
  document: Document,
  pathname: string,
  title?: string,
  resolvedCard?: HTMLElement | null,
): string | undefined {
  const match = pathname.match(/\/job_detail\/([^/.]+)(?:\.html)?/)
  if (match?.[1]) return match[1]

  const selected = resolvedCard ?? document.querySelector<HTMLElement>(
    '[data-jobid].selected,[data-job-id].selected,.job-card-wrapper.active,.job-card-wrap.active',
  )
  const selectedId = selected?.dataset.jobid ?? selected?.dataset.jobId
  if (selectedId) return selectedId

  const selectedHref = selected?.querySelector<HTMLAnchorElement>('a[href*="/job_detail/"]')
    ?.getAttribute('href')
  const selectedHrefId = selectedHref?.match(/\/job_detail\/([^/.]+)(?:\.html)?/)?.[1]
  if (selectedHrefId) return selectedHrefId

  const detailLink = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/job_detail/"]'))
    .find((link) => !title || link.textContent?.trim() === title)
  return detailLink?.getAttribute('href')?.match(/\/job_detail\/([^/.]+)(?:\.html)?/)?.[1]
}

function headerLabels(document: Document, title: string): string[] {
  const titleNode = Array.from(document.querySelectorAll('h1,.job-title,.job-name'))
    .find((node) => node.textContent?.trim().includes(title))
  const container = titleNode?.closest('.job-banner,.job-primary,.info-primary,.job-detail-info,.job-detail-box')
  if (!container) return []
  return Array.from(container.querySelectorAll('span,p,li,div'))
    .map(visibleNodeText)
    .filter(Boolean)
}

function firstMatch(values: string[], pattern: RegExp): string | undefined {
  for (const value of values) {
    const match = value.match(pattern)
    if (match?.[0]) return match[0].replace(/\s+/g, '')
  }
  return undefined
}

function cleanCompanyName(value: string | undefined): string | undefined {
  return value?.replace(/^公司名称[：:]?\s*/, '').trim() || undefined
}

function normalized(value: string | null | undefined): string {
  return value?.replace(/\s+/g, '').toLowerCase() ?? ''
}

function activeCard(document: Document, title?: string): HTMLElement | null {
  const explicitlySelected = document.querySelector<HTMLElement>(ACTIVE_CARD_SELECTOR)
  if (explicitlySelected && (!title || normalized(cardText(explicitlySelected, [
    '.job-name', '.job-title', '.job-info .name', 'a[href*="/job_detail/"]',
  ])) === normalized(title))) return explicitlySelected
  if (!title) return null
  const expected = normalized(title)
  return Array.from(document.querySelectorAll<HTMLElement>(CARD_SELECTOR)).find((card) => {
    const cardTitle = cardText(card, [
      '.job-name', '.job-title', '.job-info .name', 'a[href*="/job_detail/"]',
    ])
    return normalized(cardTitle) === expected
  }) ?? null
}

function cardText(card: HTMLElement | null, selectors: readonly string[]): string | undefined {
  if (!card) return undefined
  for (const selector of selectors) {
    const value = visibleNodeText(card.querySelector(selector))
    if (value) return value
  }
  return undefined
}

function cardCompanyName(card: HTMLElement | null): string | undefined {
  return cleanCompanyName(cardText(card, [
    'a.boss-info[href*="/gongsi/"]',
    '.boss-info a[href*="/gongsi/"]',
    '.boss-info .company-name',
    '.job-card-footer .company-name',
    '.job-card-footer [class*="company-name"]',
    '.job-card-footer .company-info a',
    '.job-card-footer .company-info',
    '.job-card-footer .name',
    '[class*="company-name"]',
    '.company-info .name',
    '.company-info a',
    '.company-text',
  ]))
}

function cardLabels(card: HTMLElement | null): string[] {
  if (!card) return []
  return Array.from(card.querySelectorAll<HTMLElement>('span,li,p,a,div'))
    .filter((node) => node.children.length === 0)
    .map(visibleNodeText)
    .filter(Boolean)
}

function semanticDescription(document: Document): string | undefined {
  const heading = Array.from(document.querySelectorAll<HTMLElement>('h1,h2,h3,h4,strong,.title'))
    .find((node) => /^(?:职位描述|岗位描述|岗位职责|职位职责)$/.test(node.textContent?.trim() ?? ''))
  const container = heading?.closest<HTMLElement>(
    'section,.job-detail-section,.job-detail-content,.job-detail-body,.detail-content',
  )
  if (!heading || !container) return undefined
  const value = visibleNodeText(container).replace(visibleNodeText(heading), '').trim()
  return value && value.length >= 10 ? value : undefined
}

function stablePartialId(page: Pick<Location, 'pathname'>, values: string[]): string {
  const input = `${page.pathname}|${values.join('|')}`
  let hash = 2166136261
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return `partial-${(hash >>> 0).toString(36)}`
}

function collectCoreFields(document: Document, page: Pick<Location, 'pathname'>) {
  const directTitle = text(document, SELECTORS.title)
  const card = activeCard(document, directTitle)
  const directCompany = cleanCompanyName(text(document, SELECTORS.company))
  const directDescription = text(document, SELECTORS.description)
  const title = directTitle ?? cardText(card, ['.job-name', '.job-title', 'a[href*="/job_detail/"]'])
  const companyName = page.pathname.startsWith('/web/geek/jobs')
    ? cardCompanyName(card) ?? directCompany
    : directCompany ?? cardCompanyName(card)
  const description = directDescription ?? semanticDescription(document)
  const directId = platformJobId(document, page.pathname, title, card)
  const hasJobSignal = Boolean(directId || title || companyName || description)
  return {
    direct: {
      platformJobId: directId,
      title: directTitle,
      companyName: directCompany,
      description: directDescription,
    },
    resolved: {
      platformJobId: directId ?? (hasJobSignal ? stablePartialId(page, [title ?? '', companyName ?? '']) : undefined),
      title: title ?? (hasJobSignal ? '职位名称待补充' : undefined),
      // A missing company is an identity failure, not a field that can be safely
      // synthesized. Returning no snapshot prevents an unknown company from
      // reaching analysis or the delivery confirmation list.
      companyName,
      description: description ?? (hasJobSignal ? '职位描述暂未采集。' : undefined),
    },
  }
}

function companySize(document: Document, card?: HTMLElement | null): string | undefined {
  const cardSize = firstMatch(cardLabels(card ?? null), COMPANY_SIZE_PATTERN)
  if (cardSize) return cardSize
  const direct = texts(document, SELECTORS.companySize)
  const company = document.querySelector('.job-detail-company,.company-info,.company-card')
  const fallback = company
    ? Array.from(company.querySelectorAll('span,li,p,div')).map(visibleNodeText)
    : []
  return firstMatch([...direct, ...fallback], COMPANY_SIZE_PATTERN)
}

export function captureBossJob(
  document: Document,
  page: Pick<Location, 'href' | 'pathname'>,
  capturedAt = new Date(),
): CapturedJob | null {
  const fields = collectCoreFields(document, page)
  const { platformJobId: id, title, companyName, description } = fields.resolved
  if (!id || !title || !companyName || !description) return null

  const card = activeCard(document, title)
  const cardValues = cardLabels(card)
  const labels = [...texts(document, SELECTORS.tags), ...headerLabels(document, title), ...cardValues]
  const uniqueLabels = [...new Set(labels)]
  const decodedSalaryLabels = uniqueLabels
    .map(label => decodeBossSalaryText(label))
    .filter((label): label is string => Boolean(label))
  return {
    platform: 'boss',
    platformJobId: id,
    url: page.href,
    title,
    companyName,
    companySize: companySize(document, card),
    location: text(document, SELECTORS.location)
      ?? cardText(card, ['.job-area', '.job-location', '.job-address', '.company-location'])
      ?? uniqueLabels.find((label) => LOCATION_PATTERN.test(label)),
    workAddress: text(document, SELECTORS.workAddress),
    salaryText: decodeBossSalaryText(text(document, SELECTORS.salary))
      ?? decodeBossSalaryText(cardText(card, ['.salary', '.job-salary']))
      ?? firstMatch(decodedSalaryLabels, SALARY_PATTERN),
    experience: uniqueLabels.find((label) => EXPERIENCE_PATTERN.test(label))?.match(EXPERIENCE_PATTERN)?.[0],
    education: uniqueLabels.find((label) => EDUCATION_PATTERN.test(label))?.match(EDUCATION_PATTERN)?.[0],
    description,
    skills: texts(document, SELECTORS.skills),
    recruiterName: text(document, SELECTORS.recruiterName),
    recruiterTitle: text(document, SELECTORS.recruiterTitle),
    capturedAt: capturedAt.toISOString(),
    source: 'dom',
  }
}

export function diagnoseBossJobCapture(
  document: Document,
  page: Pick<Location, 'href' | 'pathname'>,
): CaptureDiagnostic {
  const fields = collectCoreFields(document, page)
  const missingFields = Object.entries(fields.direct)
    .filter(([, value]) => !value)
    .map(([key]) => key)
  const recoveredFields = missingFields.filter(
    (key) => Boolean(fields.resolved[key as keyof typeof fields.resolved]),
  )
  const continued = Boolean(captureBossJob(document, page))
  return {
    level: 'warning',
    code: 'capture-incomplete',
    message: missingFields.length
      ? `部分字段未直接识别：${missingFields.join('、')}；${continued ? '已降级补全并继续处理' : '正在等待职位内容加载'}`
      : '当前页面尚未形成完整职位详情',
    details: { missingFields, recoveredFields, continued, pathname: page.pathname },
  }
}
