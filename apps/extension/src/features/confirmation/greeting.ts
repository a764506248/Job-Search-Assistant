export type ConfirmationDecision = 'confirmed' | 'cancelled' | 'expired'

export interface GreetingSendApproval {
  approved: boolean
  planApproved: boolean
  decision: ConfirmationDecision | 'confirmed_plan'
}

/**
 * The local service sets this boolean only after validating the runner's
 * private approval token and the frozen job plan. The token itself is never
 * forwarded to the extension. Calls without this server-issued proof remain
 * interactive (manual/test entry points included).
 */
export function hasConfirmedPlanApproval(payload: Record<string, unknown>): boolean {
  return payload.planConfirmed === true
}

export async function resolveGreetingSendApproval(
  payload: Record<string, unknown>,
  requestInteractiveConfirmation: () => Promise<ConfirmationDecision>,
): Promise<GreetingSendApproval> {
  if (hasConfirmedPlanApproval(payload)) {
    return { approved: true, planApproved: true, decision: 'confirmed_plan' }
  }
  const decision = await requestInteractiveConfirmation()
  return { approved: decision === 'confirmed', planApproved: false, decision }
}

export function confirmGreetingSend(
  title: string,
  company: string,
  message: string,
  timeoutMs: number,
  doc: Document = document,
): Promise<ConfirmationDecision> {
  return new Promise((resolve) => {
    doc.getElementById('job-search-assistant-confirm-greeting')?.remove()
    const host = doc.createElement('div')
    host.id = 'job-search-assistant-confirm-greeting'
    const shadow = host.attachShadow({ mode: 'open' })
    shadow.innerHTML = `<style>
      .backdrop{position:fixed;inset:0;z-index:2147483647;display:grid;place-items:center;background:rgba(8,20,16,.68);font:14px/1.5 system-ui,sans-serif}
      .card{width:min(520px,calc(100vw - 32px));padding:22px;border-radius:16px;background:#fff;color:#17251f;box-shadow:0 24px 80px rgba(0,0,0,.3)}
      h2{margin:0 0 12px;font-size:20px}.meta{margin:4px 0;color:#586a61}.message{max-height:220px;overflow:auto;margin:16px 0;padding:14px;border:1px solid #dce8e2;border-radius:10px;background:#f7faf8;white-space:pre-wrap;word-break:break-word}
      .notice{margin:8px 0;color:#8a5b00}.actions{display:flex;gap:10px;margin-top:16px}.actions button{flex:1;padding:11px;border:0;border-radius:8px;font-weight:700;cursor:pointer}.cancel{background:#edf2ef;color:#33453d}.confirm{background:#07825f;color:white}
    </style><section class="backdrop"><div class="card" role="dialog" aria-modal="true" aria-label="确认发送问候语">
      <h2>确认发送问候语</h2><p class="meta">岗位：${escapeHtml(title)}</p><p class="meta">公司：${escapeHtml(company)}</p>
      <div class="message">${escapeHtml(message)}</div><p class="notice">请在 <strong class="countdown"></strong> 秒内确认；超时不会发送。</p>
      <div class="actions"><button class="cancel">取消</button><button class="confirm">确认并发送</button></div>
    </div></section>`

    const countdown = shadow.querySelector<HTMLElement>('.countdown')!
    const startedAt = Date.now()
    const renderCountdown = () => {
      countdown.textContent = String(Math.max(0, Math.ceil((timeoutMs - (Date.now() - startedAt)) / 1000)))
    }
    const finish = (decision: ConfirmationDecision) => {
      window.clearInterval(interval)
      window.clearTimeout(timer)
      host.remove()
      resolve(decision)
    }
    renderCountdown()
    const interval = window.setInterval(renderCountdown, 250)
    const timer = window.setTimeout(() => finish('expired'), timeoutMs)
    shadow.querySelector<HTMLButtonElement>('.cancel')!.addEventListener('click', () => finish('cancelled'))
    shadow.querySelector<HTMLButtonElement>('.confirm')!.addEventListener('click', () => finish('confirmed'))
    doc.documentElement.append(host)
  })
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]!)
}
