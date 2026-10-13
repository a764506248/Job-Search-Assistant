import type { CapturedJob } from '@job-search-assistant/contracts'
import { captureBossJob } from './capture'

const CARD_SELECTOR = [
  '.job-card-wrapper',
  '.job-card-wrap',
  '.job-list-item',
  '.job-card-box',
].join(',')

const TITLE_SELECTORS = [
  '.job-name',
  '.job-info .name',
  'a[href*="/job_detail/"]',
  '.job-title',
] as const

const COMPANY_SELECTORS = [
  '.boss-name',
  'a.boss-info[href*="/gongsi/"]',
  '.boss-info a[href*="/gongsi/"]',
  '.company-name',
  '.company-info .name',
  '.job-card-footer .name',
] as const

const DEFAULT_COLLECTION_BUDGET_MS = 25_000
const DEFAULT_INITIAL_LOAD_TIMEOUT_MS = 8_000
const DEFAULT_CARD_SETTLE_TIMEOUT_MS = 4_000
const DEFAULT_LAZY_LOAD_WAIT_MS = 3_000

export type BossSearchPageState = 'ready' | 'loading' | 'empty' | 'login_required' | 'verification_required'

export interface BossSearchCollectionResult {
  jobs: CapturedJob[]
  skipped: Array<{ jobId?: string, title?: string, reason: string }>
  exhausted: boolean
  attemptedJobIds: string[]
  timeBudgetReached: boolean
  detectedCardCount: number
  pageState: BossSearchPageState
}

export interface BossSearchCollectionOptions {
  limit?: number
  itemIntervalMs?: number
  maxRounds?: number
  initialLoadTimeoutMs?: number
  settleTimeoutMs?: number
  pollMs?: number
  lazyLoadWaitMs?: number
  timeBudgetMs?: number
  excludeJobIds?: Iterable<string>
}

export async function collectBossSearchJobs(
  doc: Document,
  page: Pick<Location, 'href' | 'pathname'>,
  options: BossSearchCollectionOptions = {},
): Promise<BossSearchCollectionResult> {
  const limit = Math.max(1, Math.min(options.limit ?? 30, 100))
  const itemIntervalMs = Math.max(0, Math.min(options.itemIntervalMs ?? 0, 30_000))
  const maxRounds = Math.max(1, Math.min(options.maxRounds ?? 10, 12))
  const initialLoadTimeoutMs = Math.max(20, options.initialLoadTimeoutMs ?? DEFAULT_INITIAL_LOAD_TIMEOUT_MS)
  const settleTimeoutMs = Math.max(20, options.settleTimeoutMs ?? DEFAULT_CARD_SETTLE_TIMEOUT_MS)
  const pollMs = Math.max(1, options.pollMs ?? 100)
  const lazyLoadWaitMs = Math.max(1, options.lazyLoadWaitMs ?? DEFAULT_LAZY_LOAD_WAIT_MS)
  const timeBudgetMs = Math.max(1, options.timeBudgetMs ?? DEFAULT_COLLECTION_BUDGET_MS)
  const deadlineAt = Date.now() + timeBudgetMs
  const excludedJobIds = new Set(
    Array.from(options.excludeJobIds ?? [], value => String(value).trim()).filter(Boolean),
  )
  const jobs = new Map<string, CapturedJob>()
  const attempted = new Set<string>()
  const attemptedJobIds = new Set<string>()
  const skipped: BossSearchCollectionResult['skipped'] = []
  let unchangedRounds = 0
  let timeBudgetReached = false
  let detectedCardCount = 0
  let pageState: BossSearchPageState = 'loading'

  const initialWaitMs = Math.min(initialLoadTimeoutMs, Math.max(1, deadlineAt - Date.now()))
  const initial = await waitForInitialSearchCards(doc, page.href, initialWaitMs, pollMs)
  detectedCardCount = initial.cards.length
  pageState = initial.state
  if (!initial.cards.length) {
    timeBudgetReached = Date.now() >= deadlineAt
    return {
      jobs: [],
      skipped,
      exhausted: !timeBudgetReached && pageState !== 'loading',
      attemptedJobIds: [],
      timeBudgetReached,
      detectedCardCount,
      pageState,
    }
  }

  collection: for (let round = 0; round < maxRounds && jobs.size < limit; round += 1) {
    if (Date.now() >= deadlineAt) {
      timeBudgetReached = true
      break
    }
    const cards = searchCards(doc, page.href)
    detectedCardCount = Math.max(detectedCardCount, cards.length)
    pageState = 'ready'
    const pending = cards.filter((card) => {
      const jobId = jobIdFromHref(cardHref(card, page.href))
      return !attempted.has(cardKey(card, page.href))
        && (!jobId || !excludedJobIds.has(jobId))
    })
    if (!pending.length) unchangedRounds += 1
    else unchangedRounds = 0

    for (const card of pending) {
      if (jobs.size >= limit) break
      if (Date.now() >= deadlineAt) {
        timeBudgetReached = true
        break collection
      }
      const href = cardHref(card, page.href)
      const expectedJobId = jobIdFromHref(href)
      // Iterate selectors by semantic priority. Passing them as one selector
      // list makes querySelector return the earliest DOM node instead; on the
      // real BOSS card that is `.job-title` (title + salary), not the nested
      // `.job-name` containing the pure title used by the detail pane.
      const expectedTitle = firstCardText(card, TITLE_SELECTORS)
      const expectedCompany = firstCardText(card, COMPANY_SELECTORS)
      const key = expectedJobId || href || expectedTitle || cardKey(card, page.href)
      if (attempted.has(key)) continue
      attempted.add(key)
      if (expectedJobId) attemptedJobIds.add(expectedJobId)
      const previousDetail = readDetailState(doc, page)
      card.scrollIntoView?.({ block: 'center' })
      const link = card.querySelector<HTMLElement>('a[href*="/job_detail/"]')
      // The production BOSS page attaches its detail loader to the job link.
      // Clicking the link also bubbles to container listeners used by tests and
      // older page variants, so it remains backward compatible.
      const trigger = link ?? card
      trigger.click()

      const remainingBudgetMs = deadlineAt - Date.now()
      if (remainingBudgetMs <= 0) {
        timeBudgetReached = true
        break collection
      }

      const job = await waitForCardCapture(
        doc,
        page,
        expectedJobId,
        expectedTitle,
        expectedCompany,
        previousDetail,
        Math.min(settleTimeoutMs, remainingBudgetMs),
        pollMs,
      )
      if (!job) {
        skipped.push({
          jobId: expectedJobId,
          title: expectedTitle,
          reason: '点击岗位卡后未读取到稳定的完整职位详情',
        })
        if (Date.now() >= deadlineAt) {
          timeBudgetReached = true
          break collection
        }
        if (!await waitForCollectionInterval(itemIntervalMs, deadlineAt)) {
          timeBudgetReached = true
          break collection
        }
        continue
      }
      jobs.set(job.platformJobId, { ...job, url: href || job.url })
      if (!await waitForCollectionInterval(itemIntervalMs, deadlineAt)) {
        timeBudgetReached = true
        break collection
      }
    }

    if (jobs.size >= limit || unchangedRounds >= 2 || round + 1 >= maxRounds) break
    const beforeCardKeys = new Set(searchCards(doc, page.href).map(card => cardKey(card, page.href)))
    scrollSearchResults(doc)
    const remainingBudgetMs = deadlineAt - Date.now()
    if (remainingBudgetMs <= 0) {
      timeBudgetReached = true
      break
    }
    const waitMs = Math.min(lazyLoadWaitMs, remainingBudgetMs)
    await waitForAdditionalCards(doc, page.href, beforeCardKeys, waitMs, pollMs)
    if (waitMs < lazyLoadWaitMs || Date.now() >= deadlineAt) {
      timeBudgetReached = true
      break
    }
  }

  return {
    jobs: [...jobs.values()].slice(0, limit),
    skipped,
    // Reaching the per-call round limit does not mean the BOSS result page is
    // exhausted. Only two consecutive scroll rounds with no unseen cards are
    // strong enough evidence for the backend to stop this keyword.
    exhausted: !timeBudgetReached && unchangedRounds >= 2,
    attemptedJobIds: [...attemptedJobIds],
    timeBudgetReached,
    detectedCardCount,
    pageState,
  }
}

async function waitForCollectionInterval(intervalMs: number, deadlineAt: number): Promise<boolean> {
  if (intervalMs <= 0) return true
  const remainingBudgetMs = deadlineAt - Date.now()
  if (remainingBudgetMs < intervalMs) return false
  await delay(intervalMs)
  return true
}

async function waitForCardCapture(
  doc: Document,
  page: Pick<Location, 'href' | 'pathname'>,
  expectedJobId: string | undefined,
  expectedTitle: string | undefined,
  expectedCompany: string | undefined,
  previousDetail: DetailState,
  timeoutMs: number,
  pollMs: number,
): Promise<CapturedJob | null> {
  const deadline = Date.now() + timeoutMs
  let lastSignature = ''
  let stableMatches = 0
  while (Date.now() < deadline) {
    const job = captureBossJob(doc, page)
    const currentDetailJobId = detailJobId(doc)
    const titleMatches = !!job && normalize(job.title) === normalize(expectedTitle)
    const companyMatches = !expectedCompany
      || (!!job && normalize(job.companyName) === normalize(expectedCompany))
    const identityMatches = !!job && (
      (!!expectedJobId && (
        currentDetailJobId
          ? currentDetailJobId === expectedJobId && titleMatches && companyMatches
          : job.platformJobId === expectedJobId && titleMatches && companyMatches
      ))
      || (!expectedJobId && titleMatches && companyMatches)
    )
    const signature = job ? detailSignature(job, currentDetailJobId) : ''
    const detailChanged = previousDetail.jobId === expectedJobId
      || currentDetailJobId === expectedJobId
      || (signature && signature !== previousDetail.signature)
    if (identityMatches && detailChanged && isComplete(job)) {
      if (signature === lastSignature) stableMatches += 1
      else {
        lastSignature = signature
        stableMatches = 1
      }
      // Require two consecutive identical reads so a partially updated detail
      // pane cannot bind the previous JD to the newly selected card.
      if (stableMatches >= 2) {
        return expectedJobId ? { ...job, platformJobId: expectedJobId } : job
      }
    }
    else {
      lastSignature = ''
      stableMatches = 0
    }
    await delay(pollMs)
  }
  return null
}

interface DetailState {
  jobId?: string
  signature: string
}

function readDetailState(
  doc: Document,
  page: Pick<Location, 'href' | 'pathname'>,
): DetailState {
  const job = captureBossJob(doc, page)
  const jobId = detailJobId(doc)
  return { jobId, signature: job ? detailSignature(job, jobId) : '' }
}

function detailSignature(job: CapturedJob, detailId?: string): string {
  return [
    detailId ?? '',
    normalize(job.title),
    normalize(job.companyName),
    normalize(job.description),
  ].join('|')
}

function detailJobId(doc: Document): string | undefined {
  const link = doc.querySelector<HTMLAnchorElement>([
    '.job-detail-header a[href*="/job_detail/"]',
    '.job-detail-info a[href*="/job_detail/"]',
    '.job-detail-box a[href*="/job_detail/"]',
  ].join(','))
  return jobIdFromHref(link?.getAttribute('href') ?? '')
}

function isComplete(job: CapturedJob): boolean {
  return !job.platformJobId.startsWith('partial-')
    && !job.companyName.includes('待补充')
    && !job.description.includes('暂未采集')
    && job.description.trim().length >= 10
}

async function waitForInitialSearchCards(
  doc: Document,
  baseUrl: string,
  timeoutMs: number,
  pollMs: number,
): Promise<{ cards: HTMLElement[], state: BossSearchPageState }> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const cards = searchCards(doc, baseUrl)
    if (cards.length) return { cards, state: 'ready' }
    const state = detectSearchPageState(doc)
    if (state !== 'loading') return { cards: [], state }
    await delay(pollMs)
  }
  const cards = searchCards(doc, baseUrl)
  return {
    cards,
    state: cards.length ? 'ready' : detectSearchPageState(doc),
  }
}

async function waitForAdditionalCards(
  doc: Document,
  baseUrl: string,
  previousKeys: Set<string>,
  timeoutMs: number,
  pollMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (searchCards(doc, baseUrl).some(card => !previousKeys.has(cardKey(card, baseUrl)))) return
    await delay(pollMs)
  }
}

function searchCards(doc: Document, baseUrl: string): HTMLElement[] {
  const cards: HTMLElement[] = []
  const seen = new Set<string>()
  const links = Array.from(doc.querySelectorAll<HTMLAnchorElement>('a[href*="/job_detail/"]'))
  for (const link of links) {
    const card = link.closest<HTMLElement>('.job-card-box')
      ?? link.closest<HTMLElement>('.job-card-wrapper,.job-card-wrap,.job-list-item')
    if (!card || !card.matches(CARD_SELECTOR)) continue
    const key = jobIdFromHref(link.getAttribute('href') ?? link.href)
      ?? cardKey(card, baseUrl)
    if (!key || seen.has(key)) continue
    seen.add(key)
    cards.push(card)
  }
  return cards
}

function detectSearchPageState(doc: Document): BossSearchPageState {
  if (doc.querySelector('.geetest_panel,.geetest_holder,[class*="captcha"],[class*="verify"]')) {
    return 'verification_required'
  }
  const bodyText = (doc.body instanceof HTMLElement ? doc.body.innerText : '')
    || doc.body?.textContent
    || ''
  if (/(?:请先登录|登录后查看|手机号登录)/.test(bodyText)) return 'login_required'
  const emptyText = Array.from(doc.querySelectorAll<HTMLElement>(
    '.job-list-empty,.search-empty,.data-tips,.empty-page,.error-content',
  )).map(node => node.innerText || node.textContent || '').join(' ')
  if (/(?:暂无相关职位|没有找到相关职位|暂无职位|无搜索结果)/.test(emptyText)) return 'empty'
  return 'loading'
}

function cardHref(card: HTMLElement, baseUrl: string): string {
  const link = card.querySelector<HTMLAnchorElement>('a[href*="/job_detail/"]')
  const value = link?.getAttribute('href') || link?.href
  if (!value) return ''
  try { return new URL(value, baseUrl).toString() }
  catch { return '' }
}

function firstCardText(card: HTMLElement, selectors: readonly string[]): string | undefined {
  for (const selector of selectors) {
    const node = card.querySelector<HTMLElement>(selector)
    const value = (node?.innerText || node?.textContent || '').trim()
    if (value) return value
  }
  return undefined
}

function jobIdFromHref(href: string): string | undefined {
  return href.match(/\/job_detail\/([^/.]+)(?:\.html)?/)?.[1]
}

function cardKey(card: HTMLElement, baseUrl: string): string {
  return card.dataset.jobid
    || card.dataset.jobId
    || jobIdFromHref(cardHref(card, baseUrl))
    || normalize(card.textContent)
}

function normalize(value: string | null | undefined): string {
  return value?.replace(/\s+/g, '').toLowerCase() ?? ''
}

function scrollSearchResults(doc: Document): void {
  const cards = searchCards(doc, doc.location?.href ?? '')
  cards.at(-1)?.scrollIntoView?.({ block: 'end' })
  const container = doc.querySelector<HTMLElement>([
    '.job-list-container',
    '.job-list-box',
    '.job-list',
    '.search-job-result',
  ].join(','))
  if (container) {
    container.scrollTop = container.scrollHeight
    container.dispatchEvent(new Event('scroll', { bubbles: true }))
  }
  doc.defaultView?.scrollTo?.(0, doc.documentElement.scrollHeight)
  doc.defaultView?.dispatchEvent(new Event('scroll'))
}

function delay(milliseconds: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, milliseconds))
}
