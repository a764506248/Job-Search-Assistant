import { describe, expect, it } from 'vitest'
import { buildBossSearchUrl, normalizeBossSearchFilters } from './search'

describe('BOSS search URL', () => {
  it('applies the task-scoped collection filters', () => {
    const url = new URL(buildBossSearchUrl('AI Agent', '101010100', {
      jobType: '1901',
      salary: '406',
      experience: '105',
      degree: '206',
      industry: '100021,100020',
      scale: '304',
    }))

    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      query: 'AI Agent',
      city: '101010100',
      jobType: '1901',
      salary: '406',
      experience: '105',
      degree: '206',
      industry: '100021,100020',
      scale: '304',
    })
  })

  it('drops unknown and malformed filter values', () => {
    expect(normalizeBossSearchFilters({
      salary: '406',
      scale: 'javascript:alert(1)',
      unknown: '123',
    })).toEqual({ salary: '406' })
  })
})
