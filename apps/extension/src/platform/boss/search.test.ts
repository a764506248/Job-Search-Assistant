import { describe, expect, it } from 'vitest'
import { buildBossSearchUrl, normalizeBossSearchFilters } from './search'

describe('BOSS search URL', () => {
  it('applies the task-scoped collection filters', () => {
    const url = new URL(buildBossSearchUrl('AI Agent', '101010100', {
      jobType: '1901',
      salary: '404,405,406',
      experience: '104,105',
      degree: '203,204',
      industry: '100021,100020',
      scale: '302,303,304',
    }))

    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      query: 'AI Agent',
      city: '101010100',
      jobType: '1901',
      salary: '406',
      experience: '104,105',
      degree: '203,204',
      industry: '100021,100020',
      scale: '302,303,304',
    })
  })

  it('drops unknown and malformed filter values', () => {
    expect(normalizeBossSearchFilters({
      salary: '406',
      scale: 'javascript:alert(1)',
      unknown: '123',
    })).toEqual({ salary: '406' })
  })

  it('keeps only one salary band because BOSS salary filtering is single-select', () => {
    const url = new URL(buildBossSearchUrl('AI Agent', '101010100', {
      salary: '405,406',
      degree: '202,203',
    }))

    expect(url.searchParams.get('salary')).toBe('406')
    expect(url.searchParams.get('degree')).toBe('202,203')
    expect(normalizeBossSearchFilters({ salary: '405,406' })).toEqual({ salary: '406' })
  })
})
