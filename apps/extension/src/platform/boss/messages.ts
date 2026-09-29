import type { CapturedJob } from '@job-search-assistant/contracts'
import type { CaptureDiagnostic } from './capture'

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

export function isCaptureDiagnostic(value: unknown): value is CaptureDiagnostic {
  if (!value || typeof value !== 'object') return false
  const diagnostic = value as Partial<CaptureDiagnostic>
  return (
    (diagnostic.level === 'warning' || diagnostic.level === 'error') &&
    typeof diagnostic.code === 'string' &&
    typeof diagnostic.message === 'string' &&
    !!diagnostic.details &&
    typeof diagnostic.details === 'object'
  )
}
