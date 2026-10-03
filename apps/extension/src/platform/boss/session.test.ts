import { beforeEach, describe, expect, it } from 'vitest'
import { readBossSessionStatus } from './session'

describe('readBossSessionStatus', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it.each([
    '/web/geek/recommend?ka=header-recommend',
    '/web/geek/chat?id=conversation-1',
  ])('recognizes a logged-in BOSS navigation link: %s', (href) => {
    document.body.innerHTML = `<nav><a href="${href}">workspace</a></nav>`

    expect(readBossSessionStatus(document, {
      href: 'https://www.zhipin.com/web/geek/jobs',
      hostname: 'www.zhipin.com',
      pathname: '/web/geek/jobs',
    })).toMatchObject({ bossDomain: true, loggedIn: true })
  })

  it('does not report logged in on the login page even when stale navigation exists', () => {
    document.body.innerHTML = '<a href="/web/geek/chat">chat</a>'

    expect(readBossSessionStatus(document, {
      href: 'https://www.zhipin.com/web/user/',
      hostname: 'www.zhipin.com',
      pathname: '/web/user/',
    }).loggedIn).toBe(false)
  })

  it('requires a real BOSS domain and a signed-in navigation signal', () => {
    expect(readBossSessionStatus(document, {
      href: 'https://example.com/web/geek/jobs',
      hostname: 'example.com',
      pathname: '/web/geek/jobs',
    }).loggedIn).toBe(false)
  })
})
