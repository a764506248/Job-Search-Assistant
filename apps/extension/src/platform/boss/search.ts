export const BOSS_SEARCH_FILTER_KEYS = [
  'jobType',
  'salary',
  'experience',
  'degree',
  'industry',
  'scale',
] as const

export type BossSearchFilterKey = typeof BOSS_SEARCH_FILTER_KEYS[number]
export type BossSearchFilters = Partial<Record<BossSearchFilterKey, string>>

export function buildBossSearchUrl(
  query: string,
  cityCode: string,
  filters: BossSearchFilters = {},
): string {
  const url = new URL('https://www.zhipin.com/web/geek/jobs')
  url.searchParams.set('query', query.trim())
  if (cityCode.trim()) url.searchParams.set('city', cityCode.trim())
  for (const key of BOSS_SEARCH_FILTER_KEYS) {
    const rawValue = String(filters[key] ?? '').trim()
    const value = key === 'salary' ? rawValue.split(',').filter(Boolean).at(-1) ?? '' : rawValue
    if (value && /^\d+(?:,\d+)*$/.test(value)) url.searchParams.set(key, value)
  }
  return url.toString()
}

export function normalizeBossSearchFilters(value: unknown): BossSearchFilters {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const source = value as Record<string, unknown>
  return Object.fromEntries(
    BOSS_SEARCH_FILTER_KEYS.flatMap((key) => {
      const rawCandidate = String(source[key] ?? '').trim()
      const candidate = key === 'salary'
        ? rawCandidate.split(',').filter(Boolean).at(-1) ?? ''
        : rawCandidate
      return candidate && /^\d+(?:,\d+)*$/.test(candidate) ? [[key, candidate]] : []
    }),
  )
}
