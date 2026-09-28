import { describe, expect, it } from 'vitest'
import { isCapturedJob } from './messages'

const validJob = {
  platform: 'boss',
  platformJobId: 'job-1',
  url: 'https://www.zhipin.com/job_detail/job-1.html',
  title: '前端工程师',
  companyName: '示例公司',
  description: '负责业务开发',
  skills: ['Vue'],
  capturedAt: '2026-09-28T08:00:00.000Z',
  source: 'dom',
}

describe('isCapturedJob', () => {
  it('accepts a valid page event payload', () => {
    expect(isCapturedJob(validJob)).toBe(true)
  })

  it.each([
    null,
    { ...validJob, platform: 'other' },
    { ...validJob, description: undefined },
    { ...validJob, skills: ['Vue', 1] },
  ])('rejects an invalid or forged payload', (payload) => {
    expect(isCapturedJob(payload)).toBe(false)
  })
})
