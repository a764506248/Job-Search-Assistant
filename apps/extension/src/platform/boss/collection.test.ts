import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { collectBossSearchJobs } from './collection'

describe('collectBossSearchJobs', () => {
  beforeEach(() => { document.body.innerHTML = '' })
  afterEach(() => { vi.useRealTimers() })

  it('clicks search cards, captures stable details and keeps the detail URL', async () => {
    document.body.innerHTML = `
      <main class="job-list-container">
        <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-1.html">AI Agent 工程师</a></article>
        <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-2.html">RAG 工程师</a></article>
      </main>
      <section class="job-detail-info"><h1 class="job-name"></h1><span class="salary"></span></section>
      <section class="job-detail-company"><span class="company-name"></span></section>
      <section class="job-detail-section"><div class="job-sec-text"></div></section>
    `
    const cards = Array.from(document.querySelectorAll<HTMLElement>('.job-card-wrapper'))
    const details = [
      ['AI Agent 工程师', '甲公司', '负责 Agent、Python 与工作流平台研发'],
      ['RAG 工程师', '乙公司', '负责 RAG 检索、重排与知识库平台研发'],
    ] as const
    cards.forEach((card, index) => card.addEventListener('click', (event) => {
      event.preventDefault()
      const detail = details[index]!
      cards.forEach(item => item.classList.remove('active'))
      card.classList.add('active')
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = detail[0]
      document.querySelector<HTMLElement>('.job-detail-company .company-name')!.textContent = detail[1]
      document.querySelector<HTMLElement>('.job-detail-section .job-sec-text')!.textContent = detail[2]
    }))

    const result = await collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs?query=AI', pathname: '/web/geek/jobs' },
      { limit: 2, settleTimeoutMs: 100, pollMs: 1 },
    )

    expect(result.jobs).toHaveLength(2)
    expect(result.jobs.map(job => job.platformJobId)).toEqual(['job-1', 'job-2'])
    expect(result.jobs.map(job => job.companyName)).toEqual(['甲公司', '乙公司'])
    expect(result.jobs[1]!.url).toBe('https://www.zhipin.com/job_detail/job-2.html')
  })

  it('waits for asynchronously rendered search cards before declaring the page empty', async () => {
    vi.useFakeTimers()
    document.body.innerHTML = `
      <main class="job-list-container"></main>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-company"><span class="company-name"></span></section>
      <section class="job-detail-body"><p class="desc"></p></section>
    `
    setTimeout(() => {
      const container = document.querySelector<HTMLElement>('.job-list-container')!
      container.innerHTML = '<div class="job-card-wrap"><li class="job-card-box"><a class="job-name" href="/job_detail/async-1.html">Agent 工程师</a><a class="boss-info" href="/gongsi/a.html">异步智能</a></li></div>'
      container.querySelector('.job-name')!.addEventListener('click', (event) => {
        event.preventDefault()
        container.querySelector('.job-card-wrap')!.classList.add('active')
        document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'Agent 工程师'
        document.querySelector<HTMLElement>('.job-detail-company .company-name')!.textContent = '异步智能'
        document.querySelector<HTMLElement>('.job-detail-body .desc')!.textContent = '负责 Agent 工作流与 Python 服务开发'
      })
    }, 1_500)

    const pending = collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs?query=Agent', pathname: '/web/geek/jobs' },
      { limit: 1, initialLoadTimeoutMs: 3_000, settleTimeoutMs: 500, pollMs: 50, timeBudgetMs: 5_000 },
    )
    await vi.runAllTimersAsync()
    const result = await pending

    expect(result.jobs.map(job => job.platformJobId)).toEqual(['async-1'])
    expect(result.detectedCardCount).toBe(1)
    expect(result.pageState).toBe('ready')
  })

  it('waits for a slowly rendered detail pane within the action budget', async () => {
    vi.useFakeTimers()
    document.body.innerHTML = `
      <div class="job-card-wrap"><li class="job-card-box"><a class="job-name" href="/job_detail/slow-1.html">RAG 工程师</a><a class="boss-info" href="/gongsi/b.html">慢速科技</a></li></div>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-company"><span class="company-name"></span></section>
      <section class="job-detail-body"><p class="desc"></p></section>
      <section class="job-detail-box"><a class="more-job-btn"></a></section>
    `
    const card = document.querySelector<HTMLElement>('.job-card-wrap')!
    card.querySelector('.job-name')!.addEventListener('click', (event) => {
      event.preventDefault()
      card.classList.add('active')
      setTimeout(() => {
        document.querySelector<HTMLAnchorElement>('.more-job-btn')!.href = '/job_detail/slow-1.html'
        document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'RAG 工程师'
        document.querySelector<HTMLElement>('.job-detail-company .company-name')!.textContent = '慢速科技'
        document.querySelector<HTMLElement>('.job-detail-body .desc')!.textContent = '负责 RAG 检索、重排与知识库平台开发'
      }, 3_000)
    })

    const pending = collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs?query=RAG', pathname: '/web/geek/jobs' },
      { limit: 1, settleTimeoutMs: 3_800, pollMs: 100, timeBudgetMs: 5_000 },
    )
    await vi.runAllTimersAsync()
    const result = await pending

    expect(result.jobs.map(job => job.platformJobId)).toEqual(['slow-1'])
    expect(result.skipped).toEqual([])
  })

  it('deduplicates multiple detail links that belong to the same card', async () => {
    document.body.innerHTML = `
      <div class="job-card-wrap"><li class="job-card-box"><a class="job-name" href="/job_detail/double-1.html">Agent 平台工程师</a><a class="job-logo" href="/job_detail/double-1.html">图标</a><a class="boss-info" href="/gongsi/c.html">双链科技</a></li></div>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-company"><span class="company-name"></span></section>
      <section class="job-detail-body"><p class="desc"></p></section>
    `
    const card = document.querySelector<HTMLElement>('.job-card-wrap')!
    card.addEventListener('click', (event) => {
      event.preventDefault()
      card.classList.add('active')
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'Agent 平台工程师'
      document.querySelector<HTMLElement>('.job-detail-company .company-name')!.textContent = '双链科技'
      document.querySelector<HTMLElement>('.job-detail-body .desc')!.textContent = '负责 Agent 平台和可观测系统开发'
    })

    const result = await collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs?query=Agent', pathname: '/web/geek/jobs' },
      { limit: 1, settleTimeoutMs: 100, pollMs: 1 },
    )

    expect(result.jobs.map(job => job.platformJobId)).toEqual(['double-1'])
    expect(result.attemptedJobIds).toEqual(['double-1'])
  })

  it('skips cards whose detail pane never becomes complete', async () => {
    document.body.innerHTML = `
      <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-1.html">AI 工程师</a></article>
      <section class="job-detail-info"><h1 class="job-name">AI 工程师</h1></section>
    `

    const result = await collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs', pathname: '/web/geek/jobs' },
      { limit: 1, maxRounds: 1, settleTimeoutMs: 20, pollMs: 1 },
    )

    expect(result.jobs).toEqual([])
    expect(result.skipped[0]).toMatchObject({ jobId: 'job-1' })
  })

  it('loads additional cards, skips duplicate containers and keeps collection order', async () => {
    document.body.innerHTML = `
      <main class="job-list-container">
        <div class="job-card-wrap">
          <li class="job-card-box"><a class="job-name" href="/job_detail/job-1.html">Agent 工程师</a><span class="boss-name">甲公司</span></li>
        </div>
      </main>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-company"><span class="company-name"></span></section>
      <section class="job-detail-section"><div class="job-sec-text"></div></section>
    `
    const container = document.querySelector<HTMLElement>('.job-list-container')!
    let appended = false
    Object.defineProperty(container, 'scrollTop', {
      configurable: true,
      set() {
        if (appended) return
        appended = true
        container.insertAdjacentHTML('beforeend', `
          <li class="job-card-box"><a class="job-name" href="/job_detail/job-2.html">RAG 工程师</a><span class="boss-name">乙公司</span></li>
        `)
      },
    })
    document.body.addEventListener('click', (event) => {
      const card = (event.target as HTMLElement).closest<HTMLElement>('.job-card-box')
      if (!card) return
      event.preventDefault()
      document.querySelectorAll('.job-card-box').forEach(item => item.classList.remove('active'))
      card.classList.add('active')
      const jobId = card.querySelector('a')?.getAttribute('href')?.includes('job-2') ? 'job-2' : 'job-1'
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = jobId === 'job-2' ? 'RAG 工程师' : 'Agent 工程师'
      document.querySelector<HTMLElement>('.job-detail-company .company-name')!.textContent = jobId === 'job-2' ? '乙公司' : '甲公司'
      document.querySelector<HTMLElement>('.job-detail-section .job-sec-text')!.textContent = `负责 ${jobId} 对应的平台研发与稳定性建设`
    })

    const startedAt = Date.now()
    const result = await collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs', pathname: '/web/geek/jobs' },
      {
        limit: 2,
        maxRounds: 3,
        settleTimeoutMs: 100,
        pollMs: 1,
        lazyLoadWaitMs: 1,
        itemIntervalMs: 20,
      },
    )

    expect(result.jobs.map(job => job.platformJobId)).toEqual(['job-1', 'job-2'])
    expect(result.jobs.map(job => job.companyName)).toEqual(['甲公司', '乙公司'])
    expect(Date.now() - startedAt).toBeGreaterThanOrEqual(20)
  })

  it('clicks the real job link and excludes job ids collected by an earlier batch', async () => {
    document.body.innerHTML = `
      <main class="job-list-container">
        <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-1.html">Agent 工程师</a><a class="boss-info" href="/gongsi/company-1.html">甲公司</a></article>
        <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-2.html">RAG 工程师</a><a class="boss-info" href="/gongsi/company-2.html">乙公司</a></article>
      </main>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-section"><div class="job-sec-text"></div></section>
    `
    const excludedLink = document.querySelector<HTMLAnchorElement>('a[href*="job-1"]')!
    const includedLink = document.querySelector<HTMLAnchorElement>('a[href*="job-2"]')!
    const excludedClick = vi.fn(event => event.preventDefault())
    excludedLink.addEventListener('click', excludedClick)
    includedLink.addEventListener('click', (event) => {
      event.preventDefault()
      includedLink.closest('.job-card-wrapper')?.classList.add('active')
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'RAG 工程师'
      document.querySelector<HTMLElement>('.job-detail-section .job-sec-text')!.textContent = '负责 RAG 检索、重排和知识库平台开发'
    })

    const result = await collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs', pathname: '/web/geek/jobs' },
      { limit: 1, excludeJobIds: ['job-1'], settleTimeoutMs: 100, pollMs: 1 },
    )

    expect(excludedClick).not.toHaveBeenCalled()
    expect(result.jobs.map(job => job.platformJobId)).toEqual(['job-2'])
    expect(result.jobs[0]?.companyName).toBe('乙公司')
    expect(result.attemptedJobIds).toEqual(['job-2'])
  })

  it('uses the nested BOSS job-name instead of the job-title wrapper containing salary', async () => {
    document.body.innerHTML = `
      <main class="job-list-container">
        <div class="job-card-wrap">
          <li class="job-card-box">
            <div class="job-info">
              <div class="job-title clearfix">
                <a class="job-name" href="/job_detail/real-card-1.html">AI Agent开发工程师（兼职）</a>
                <span class="job-salary">80-120元/时</span>
              </div>
            </div>
            <div class="job-card-footer">
              <a class="boss-info" href="/gongsi/real-company.html"><span class="boss-name">电能趋势</span></a>
            </div>
          </li>
        </div>
      </main>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-company"><span class="company-name"></span></section>
      <section class="job-detail-body"><p class="desc"></p></section>
      <section class="job-detail-box"><a class="more-job-btn"></a></section>
    `
    const card = document.querySelector<HTMLElement>('.job-card-wrap')!
    card.querySelector('.job-name')!.addEventListener('click', (event) => {
      event.preventDefault()
      event.stopPropagation()
      card.classList.add('active')
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'AI Agent开发工程师（兼职）'
      document.querySelector<HTMLElement>('.job-detail-company .company-name')!.textContent = '电能趋势'
      document.querySelector<HTMLElement>('.job-detail-body .desc')!.textContent = '负责设计、开发和部署基于大语言模型的 AI Agent 系统'
      document.querySelector<HTMLAnchorElement>('.more-job-btn')!.href = '/job_detail/real-card-1.html'
    })

    const result = await collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs?query=Agent', pathname: '/web/geek/jobs' },
      { limit: 1, settleTimeoutMs: 100, pollMs: 1 },
    )

    expect(result.jobs).toHaveLength(1)
    expect(result.jobs[0]).toMatchObject({
      platformJobId: 'real-card-1',
      title: 'AI Agent开发工程师（兼职）',
      companyName: '电能趋势',
    })
  })

  it('returns collected partial results before the total time budget expires', async () => {
    vi.useFakeTimers()
    document.body.innerHTML = `
      <main class="job-list-container">
        <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-1.html">Agent 工程师</a><a class="boss-info" href="/gongsi/company-1.html">甲公司</a></article>
        <article class="job-card-wrapper"><a class="job-name" href="/job_detail/job-2.html">RAG 工程师</a><a class="boss-info" href="/gongsi/company-2.html">乙公司</a></article>
      </main>
      <section class="job-detail-info"><h1 class="job-name"></h1></section>
      <section class="job-detail-section"><div class="job-sec-text"></div></section>
    `
    const links = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/job_detail/"]'))
    links[0]!.addEventListener('click', (event) => {
      event.preventDefault()
      links[0]!.closest('.job-card-wrapper')?.classList.add('active')
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'Agent 工程师'
      document.querySelector<HTMLElement>('.job-detail-section .job-sec-text')!.textContent = '负责 Agent、Python 和工作流平台开发'
    })
    links[1]!.addEventListener('click', (event) => {
      event.preventDefault()
      document.querySelectorAll('.job-card-wrapper').forEach(item => item.classList.remove('active'))
      links[1]!.closest('.job-card-wrapper')?.classList.add('active')
      document.querySelector<HTMLElement>('.job-detail-info .job-name')!.textContent = 'RAG 工程师'
      document.querySelector<HTMLElement>('.job-detail-section .job-sec-text')!.textContent = ''
    })

    const pending = collectBossSearchJobs(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs', pathname: '/web/geek/jobs' },
      { limit: 2, maxRounds: 1, settleTimeoutMs: 100, pollMs: 10, timeBudgetMs: 60 },
    )
    await vi.runAllTimersAsync()
    const result = await pending

    expect(result.jobs.map(job => job.platformJobId)).toEqual(['job-1'])
    expect(result.attemptedJobIds).toEqual(['job-1', 'job-2'])
    expect(result.timeBudgetReached).toBe(true)
    expect(result.exhausted).toBe(false)
    expect(result.skipped).toEqual([
      expect.objectContaining({ jobId: 'job-2' }),
    ])
  })
})
