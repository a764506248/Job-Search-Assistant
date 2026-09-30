import { beforeEach, describe, expect, it } from 'vitest'
import { captureBossJob, diagnoseBossJobCapture } from './capture'

describe('captureBossJob', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('extracts a complete job detail from the Boss DOM', () => {
    document.body.innerHTML = `
      <section class="job-detail-info">
        <div class="name"><h1>高级前端工程师</h1></div>
        <span class="salary">25-35K</span>
        <span class="text-desc">上海·浦东新区</span>
        <ul class="tag-list"><li>3-5年</li><li>本科</li></ul>
      </section>
      <section class="job-detail-company"><div class="company-name">示例科技</div></section>
      <section class="job-detail-section">
        <div class="job-sec-text">负责 Vue 与 TypeScript 项目开发</div>
        <div class="job-tags"><span>Vue</span><span>TypeScript</span><span>Vue</span></div>
      </section>
      <section class="job-location"><div class="location-address">上海市浦东新区张江路 88 号</div></section>
      <section class="boss-info-attr"><span class="name">李女士</span><span class="boss-info-label">招聘经理</span></section>
    `

    const result = captureBossJob(
      document,
      { href: 'https://www.zhipin.com/job_detail/abc123.html', pathname: '/job_detail/abc123.html' },
      new Date('2026-09-28T08:00:00.000Z'),
    )

    expect(result).toMatchObject({
      platform: 'boss',
      platformJobId: 'abc123',
      title: '高级前端工程师',
      companyName: '示例科技',
      location: '上海·浦东新区',
      workAddress: '上海市浦东新区张江路 88 号',
      salaryText: '25-35K',
      experience: '3-5年',
      education: '本科',
      skills: ['Vue', 'TypeScript'],
      recruiterName: '李女士',
      recruiterTitle: '招聘经理',
      capturedAt: '2026-09-28T08:00:00.000Z',
      source: 'dom',
    })
  })

  it('uses the selected list card job id as a fallback', () => {
    document.body.innerHTML = `
      <article class="job-card-wrapper active" data-jobid="list-42"></article>
      <h1 class="job-title">后端工程师</h1>
      <div class="company-info"><span class="company-name">本地公司</span></div>
      <div class="job-sec-text">负责 API 开发</div>
    `

    expect(captureBossJob(document, { href: 'https://www.zhipin.com/web/geek/job', pathname: '/web/geek/job' }))
      .toMatchObject({ platformJobId: 'list-42', title: '后端工程师' })
  })

  it('extracts the current job id from its detail link on the job list page', () => {
    document.body.innerHTML = `
      <div class="job-card-wrap active"><li><div class="job-title"><a class="job-name" href="/job_detail/list-current.html">AI Agent 工程师</a></div></li></div>
      <div class="job-detail-header">
        <div class="job-detail-info"><span class="job-name">AI Agent 工程师</span></div>
        <ul><li><a>北京</a></li><li><span>3-5年</span></li><li><span>本科</span></li></ul>
      </div>
      <div class="job-detail-company"><span class="company-name">示例智能科技</span></div>
      <div class="job-sec-text">负责 LangGraph、RAG 和 Agent 平台开发</div>
    `

    expect(captureBossJob(document, { href: 'https://www.zhipin.com/web/geek/jobs?degree=202', pathname: '/web/geek/jobs' }))
      .toMatchObject({ platformJobId: 'list-current', title: 'AI Agent 工程师', location: '北京', experience: '3-5年', education: '本科' })
  })

  it('matches the visible list card by title when Boss does not mark it active', () => {
    document.body.innerHTML = `
      <div class="job-card-wrapper">
        <a class="job-name" href="/job_detail/other-job.html">高级全栈工程师</a>
        <span class="salary">28-40K·15薪</span>
        <div class="job-card-footer"><span class="company-name">Willand未岚大陆</span><span class="job-area">北京·海淀区</span></div>
      </div>
      <div class="job-card-wrapper">
        <a class="job-name" href="/job_detail/ad-algorithm.html">广告算法专家</a>
        <span class="salary">45-75K·15薪</span>
        <ul><li>5-10年</li><li>本科</li><li>Python</li></ul>
        <div class="job-card-footer"><span class="company-name">HUNGRY STUDIO</span><span class="job-area">北京·朝阳区·亚运村</span></div>
      </div>
      <section class="job-detail-info"><h1 class="job-name">广告算法专家</h1></section>
      <section class="job-detail-section"><div class="job-sec-text">负责广告推荐算法、深度学习和大数据平台研发。</div></section>
    `

    const result = captureBossJob(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs?ka=header-jobs', pathname: '/web/geek/jobs' },
    )

    expect(result).toMatchObject({
      platformJobId: 'ad-algorithm',
      title: '广告算法专家',
      companyName: 'HUNGRY STUDIO',
      salaryText: '45-75K·15薪',
      location: '北京·朝阳区·亚运村',
      experience: '5-10年',
      education: '本科',
    })
  })

  it('extracts salary, city, experience and education from the current job banner', () => {
    document.body.innerHTML = `
      <section class="job-banner">
        <div class="job-primary"><div class="info-primary">
          <div class="name"><h1 class="job-title">高级Python全栈工程师（精通AIGC开发）</h1><span class="salary">25-50K</span></div>
          <p><span class="text-desc text-city">北京</span><span class="text-desc">5-10年</span><span class="text-desc">本科</span></p>
        </div></div>
      </section>
      <aside class="company-info"><span class="company-name">公司名称天津元数昇科技有限公司北京分公司</span><ul class="company-tag-list"><li>100-499人</li></ul></aside>
      <section class="job-detail-section"><div class="job-sec-text">负责 Python、Agent 和 RAG 平台开发。</div></section>
    `

    const result = captureBossJob(
      document,
      { href: 'https://www.zhipin.com/job_detail/current-1.html', pathname: '/job_detail/current-1.html' },
    )

    expect(result).toMatchObject({
      companyName: '天津元数昇科技有限公司北京分公司',
      companySize: '100-499人',
      salaryText: '25-50K',
      location: '北京',
      experience: '5-10年',
      education: '本科',
    })
  })

  it('falls back to formatted header text when metadata classes change', () => {
    document.body.innerHTML = `
      <section class="job-primary"><h1 class="job-title">AI Agent 工程师</h1>
        <div>30-50K·14薪</div><div>北京</div><div>3-5年</div><div>本科</div>
      </section>
      <div class="company-info">公司名称示例智能科技</div>
      <div class="job-sec-text">负责 Agent 平台开发</div>
    `
    const result = captureBossJob(
      document,
      { href: 'https://www.zhipin.com/job_detail/fallback-1.html', pathname: '/job_detail/fallback-1.html' },
    )
    expect(result).toMatchObject({ salaryText: '30-50K·14薪', location: '北京', experience: '3-5年', education: '本科' })
  })

  it('continues with a partial snapshot when optional core fields are missing', () => {
    document.body.innerHTML = '<h1 class="job-title">缺少公司和 JD</h1>'
    const page = {
      href: 'https://www.zhipin.com/job_detail/empty.html',
      pathname: '/job_detail/empty.html',
    }
    expect(captureBossJob(document, page)).toMatchObject({
      platformJobId: 'empty',
      title: '缺少公司和 JD',
      companyName: '公司名称待补充',
      description: '职位描述暂未采集。',
    })
    expect(diagnoseBossJobCapture(document, page)).toMatchObject({
      level: 'warning',
      details: {
        missingFields: ['companyName', 'description'],
        recoveredFields: ['companyName', 'description'],
        continued: true,
      },
    })
  })

  it('waits when the page has no job signal at all', () => {
    document.body.innerHTML = '<main>职位内容加载中</main>'
    expect(captureBossJob(
      document,
      { href: 'https://www.zhipin.com/web/geek/jobs', pathname: '/web/geek/jobs' },
    )).toBeNull()
  })
})
