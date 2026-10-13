import type { BrowserAction, BrowserActionResult } from './protocol'

const RELOAD_SAFE_ACTIONS = new Set<BrowserAction>([
  'session_status',
  'capture_job',
  'collect_jobs',
  'validate_identity',
])

export interface ContentScriptRecoveryDriver {
  reloadAndWaitForComplete: () => Promise<void>
  waitForReceiver: () => Promise<void>
  retryOnce: () => Promise<Omit<BrowserActionResult, 'requestId'>>
}

export function canReloadAndRetryAction(action: BrowserAction): boolean {
  return RELOAD_SAFE_ACTIONS.has(action)
}

export async function reloadContentScriptAndRetryOnce(
  action: BrowserAction,
  driver: ContentScriptRecoveryDriver,
): Promise<Omit<BrowserActionResult, 'requestId'>> {
  if (!canReloadAndRetryAction(action)) {
    throw new Error(`browser action is not safe to reload and retry: ${action}`)
  }
  await driver.reloadAndWaitForComplete()
  await driver.waitForReceiver()
  return driver.retryOnce()
}
