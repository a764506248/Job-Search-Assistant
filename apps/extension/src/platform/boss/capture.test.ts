import { beforeEach, describe, expect, it } from 'vitest'
import { captureBossJob } from './capture'

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

  it('does not emit incomplete jobs', () => {
    document.body.innerHTML = '<h1 class="job-title">缺少公司和 JD</h1>'
    expect(captureBossJob(document, { href: 'https://www.zhipin.com/job_detail/empty.html', pathname: '/job_detail/empty.html' })).toBeNull()
  })
})
