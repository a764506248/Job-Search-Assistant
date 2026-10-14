import { describe, expect, it } from 'vitest'
import { normalizeRecruiterActivity } from './recruiter-activity'

describe('normalizeRecruiterActivity', () => {
  it.each([
    ['在线', 'online'],
    ['刚刚活跃', 'just_now'],
    ['刚刚在线', 'just_now'],
    ['今日活跃', 'today'],
    ['3日内活跃', 'within_3_days'],
    ['三日内活跃', 'within_3_days'],
    ['近3天活跃', 'within_3_days'],
    ['本周活跃', 'this_week'],
    ['本月活跃', 'this_month'],
    ['上周活跃', 'older'],
    ['', 'unknown'],
    ['状态不可见', 'unknown'],
  ] as const)('%s → %s', (input, expected) => {
    expect(normalizeRecruiterActivity(input)).toBe(expected)
  })
})
