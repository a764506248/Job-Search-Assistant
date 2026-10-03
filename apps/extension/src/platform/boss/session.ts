export interface BossSessionStatus {
  url: string
  bossDomain: boolean
  documentReady: boolean
  loggedIn: boolean
}

const SESSION_LINK_SELECTOR = [
  'a[href*="/web/geek/recommend"]',
  'a[href*="/web/geek/chat"]',
].join(',')

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
  }
}
