export interface BossSessionStatus {
  url: string
  bossDomain: boolean
  documentReady: boolean
  loggedIn: boolean
  accountName?: string
}

const SESSION_LINK_SELECTOR = [
  'a[href*="/web/geek/recommend"]',
  'a[href*="/web/geek/chat"]',
].join(',')

const ACCOUNT_NAME_SELECTORS = [
  '.user-nav .name',
  '.nav-figure .name',
  '.nav-figure .label-text',
  '[ka="header-personal"] .name',
  '[ka="header-personal"]',
]

function readAccountName(doc: Document): string | undefined {
  for (const selector of ACCOUNT_NAME_SELECTORS) {
    const raw = doc.querySelector<HTMLElement>(selector)?.innerText?.trim()
    const value = raw?.replace(/\s*new\s*/gi, '').split(/\s+/)[0]?.trim()
    if (value && value.length <= 20 && !['简历', '消息', '我的'].includes(value)) return value
  }
  return undefined
}

export function readBossSessionStatus(
  doc: Document,
  page: Pick<Location, 'href' | 'hostname' | 'pathname'>,
): BossSessionStatus {
  const bossDomain = /(^|\.)zhipin\.com$/i.test(page.hostname)
  const loginPage = /(?:^|\/)(?:login|register)(?:\/|$)/i.test(page.pathname)
    || page.pathname.startsWith('/web/user')
  const sessionNavigationVisible = Boolean(doc.querySelector(SESSION_LINK_SELECTOR))

  return {
    url: page.href,
    bossDomain,
    documentReady: doc.readyState === 'complete',
    loggedIn: bossDomain && !loginPage && sessionNavigationVisible,
    accountName: readAccountName(doc),
  }
}
