import type { CapturedJob } from '@job-search-assistant/contracts'

export function isCapturedJob(value: unknown): value is CapturedJob {
  if (!value || typeof value !== 'object') return false
  const job = value as Partial<CapturedJob>
  return (
    job.platform === 'boss' &&
    typeof job.platformJobId === 'string' &&
    typeof job.url === 'string' &&
    typeof job.title === 'string' &&
    typeof job.companyName === 'string' &&
    typeof job.description === 'string' &&
    Array.isArray(job.skills) &&
    job.skills.every((skill) => typeof skill === 'string')
  )
}
