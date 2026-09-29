import type { AutomaticJobMatchResponse, CapturedJob } from '@job-search-assistant/contracts'

export interface JobAnalysisPanel {
  showIdle(message?: string): void
  showLoading(job: CapturedJob): void
  showResult(job: CapturedJob, result: AutomaticJobMatchResponse): void
  showError(job: CapturedJob | null, message: string): void
  reportDiagnostic(diagnostic: PanelDiagnostic): void
  clearDiagnostic(code: string): void
  destroy(): void
}

export interface PanelDiagnostic {
  level: 'warning' | 'error'
  code: string
  message: string
  details?: Record<string, unknown>
}

const strategyLabels = {
  custom: '定制简历 + 定制问候语',
  default: '默认简历 + 默认问候语',
  blocked: '不投递',
} as const

export function mountJobAnalysisPanel(document: Document): JobAnalysisPanel {
  document.querySelector('#job-search-assistant-host')?.remove()
  const host = document.createElement('div')
  host.id = 'job-search-assistant-host'
  const shadow = host.attachShadow({ mode: 'open' })
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; }
      .panel { position: fixed; z-index: 2147483647; right: 24px; bottom: 24px; width: 360px; max-height: calc(100vh - 48px); overflow: auto; border: 1px solid #d9e4de; border-radius: 16px; background: #fff; color: #17342b; box-shadow: 0 20px 60px rgba(18, 46, 37, .2); font: 13px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      .head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; background: #123e32; color: #f5fff9; }
      .logo { display: grid; place-items: center; width: 30px; height: 30px; flex: 0 0 auto; border-radius: 9px; background: #d8f4e7; color: #123e32; font-weight: 900; }
      .heading { min-width: 0; flex: 1; }
      .heading strong, .heading span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .heading span { color: #bcd7cd; font-size: 11px; }
      button { border: 0; cursor: pointer; font: inherit; }
      .toggle { width: 28px; height: 28px; border-radius: 8px; background: rgba(255,255,255,.1); color: #fff; }
      .body { padding: 15px 16px 17px; }
      .tabs { display: flex; gap: 4px; padding: 8px 12px 0; border-bottom: 1px solid #e6ece8; background: #fff; }
      .tab { padding: 7px 10px; border-bottom: 2px solid transparent; background: transparent; color: #687870; font-size: 11px; }
      .tab.active { border-bottom-color: #14775d; color: #14775d; font-weight: 700; }
      .tab .badge { display: inline-grid; min-width: 17px; height: 17px; margin-left: 4px; padding: 0 4px; place-items: center; border-radius: 9px; background: #b8493f; color: #fff; font-size: 9px; }
      .diagnostics { display: none; padding: 12px 16px 17px; }
      .diagnostics.active, .body.active { display: block; }
      .body:not(.active) { display: none; }
      .panel.collapsed .body, .panel.collapsed .tabs, .panel.collapsed .diagnostics { display: none; }
      .diagnostic-empty { margin: 0; color: #687870; font-size: 11px; }
      .diagnostic { padding: 9px 0; border-top: 1px solid #e6ece8; }
      .diagnostic:first-child { border-top: 0; }
      .diagnostic header { display: flex; justify-content: space-between; gap: 8px; }
      .diagnostic strong { color: #9a4e24; font-size: 11px; }
      .diagnostic.error strong { color: #a23d35; }
      .diagnostic time { color: #87958e; font-size: 9px; }
      .diagnostic p { margin: 5px 0 0; color: #586a61; font-size: 10px; overflow-wrap: anywhere; }
      .diagnostic code { display: block; margin-top: 5px; color: #7b8982; font: 9px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
      .status { margin: 0; color: #687870; font-size: 12px; }
      .loading::before { content: ''; display: inline-block; width: 9px; height: 9px; margin-right: 7px; border: 2px solid #bdd8cd; border-top-color: #14775d; border-radius: 50%; animation: spin .75s linear infinite; }
      @keyframes spin { to { transform: rotate(360deg); } }
      .scores { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-bottom: 11px; }
      .score { padding: 11px; border-radius: 10px; background: #f3f7f5; }
      .score span { display: block; color: #708078; font-size: 10px; }
      .score strong { display: block; margin-top: 3px; color: #14775d; font-size: 20px; }
      .strategy { padding: 11px 12px; border-radius: 10px; background: #eaf6f1; }
      .strategy span { display: block; color: #62746c; font-size: 10px; }
      .strategy strong { display: block; margin-top: 3px; color: #116e56; }
      .risks, .evidence { margin-top: 13px; }
      h3 { margin: 0 0 7px; font-size: 12px; }
      .risk { margin: 5px 0; padding: 7px 9px; border-radius: 8px; background: #fff4e5; color: #8a5718; font-size: 11px; }
      .evidence article { padding: 9px 0; border-top: 1px solid #e6ece8; }
      .evidence article:first-of-type { border-top: 0; }
      .evidence header { display: flex; justify-content: space-between; gap: 10px; font-size: 10px; }
      .evidence header span { color: #14775d; white-space: nowrap; }
      .evidence p { display: -webkit-box; margin: 5px 0 0; overflow: hidden; color: #64736c; font-size: 10px; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
      .error { color: #a23d35; }
      @media (max-width: 600px) { .panel { right: 12px; bottom: 12px; width: calc(100vw - 24px); } }
    </style>
    <section class="panel" aria-label="Job Search Assistant 职位分析">
      <header class="head"><span class="logo">J</span><div class="heading"><strong>Job Search Assistant</strong><span id="job-title">等待职位信息</span></div><button class="toggle" type="button" aria-label="收起分析面板">−</button></header>
      <nav class="tabs"><button class="tab active" data-tab="analysis" type="button">分析</button><button class="tab" data-tab="errors" type="button">告警<span class="badge" hidden>0</span></button></nav>
      <main class="body active"><p class="status">打开 Boss 职位详情后，将自动分析当前岗位。</p></main>
      <aside class="diagnostics"><p class="diagnostic-empty">暂无告警</p></aside>
    </section>`
  document.documentElement.append(host)

  const panel = shadow.querySelector<HTMLElement>('.panel')!
  const title = shadow.querySelector<HTMLElement>('#job-title')!
  const body = shadow.querySelector<HTMLElement>('.body')!
  const diagnosticsBody = shadow.querySelector<HTMLElement>('.diagnostics')!
  const tabButtons = Array.from(shadow.querySelectorAll<HTMLButtonElement>('.tab'))
  const badge = shadow.querySelector<HTMLElement>('.badge')!
  const toggle = shadow.querySelector<HTMLButtonElement>('.toggle')!
  const diagnostics: Array<PanelDiagnostic & { occurredAt: Date }> = []

  const selectTab = (name: string) => {
    tabButtons.forEach((button) => button.classList.toggle('active', button.dataset.tab === name))
    body.classList.toggle('active', name === 'analysis')
    diagnosticsBody.classList.toggle('active', name === 'errors')
  }
  tabButtons.forEach((button) => button.addEventListener('click', () => selectTab(button.dataset.tab ?? 'analysis')))
  toggle.addEventListener('click', () => {
    const collapsed = panel.classList.toggle('collapsed')
    toggle.textContent = collapsed ? '+' : '−'
    toggle.setAttribute('aria-label', collapsed ? '展开分析面板' : '收起分析面板')
  })

  const setTitle = (job: CapturedJob | null) => {
    title.textContent = job ? `${job.title} · ${job.companyName}` : '等待职位信息'
  }
  const setMessage = (message: string, className = 'status') => {
    body.replaceChildren()
    const paragraph = document.createElement('p')
    paragraph.className = className
    paragraph.textContent = message
    body.append(paragraph)
  }
  const renderDiagnostics = () => {
    diagnosticsBody.replaceChildren()
    badge.textContent = String(diagnostics.length)
    badge.hidden = diagnostics.length === 0
    if (!diagnostics.length) {
      const empty = document.createElement('p')
      empty.className = 'diagnostic-empty'
      empty.textContent = '暂无告警'
      diagnosticsBody.append(empty)
      return
    }
    for (const item of diagnostics.slice(0, 20)) {
      const article = document.createElement('article')
      article.className = `diagnostic ${item.level}`
      const header = document.createElement('header')
      const code = document.createElement('strong')
      code.textContent = item.code
      const time = document.createElement('time')
      time.textContent = item.occurredAt.toLocaleTimeString('zh-CN', { hour12: false })
      header.append(code, time)
      const message = document.createElement('p')
      message.textContent = item.message
      article.append(header, message)
      if (item.details && Object.keys(item.details).length) {
        const details = document.createElement('code')
        details.textContent = JSON.stringify(item.details)
        article.append(details)
      }
      diagnosticsBody.append(article)
    }
  }
  const reportDiagnostic = (diagnostic: PanelDiagnostic) => {
    const previous = diagnostics[0]
    if (previous?.code === diagnostic.code && previous.message === diagnostic.message) return
    diagnostics.unshift({ ...diagnostic, occurredAt: new Date() })
    renderDiagnostics()
  }
  const clearDiagnostic = (code: string) => {
    const remaining = diagnostics.filter((item) => item.code !== code)
    if (remaining.length === diagnostics.length) return
    diagnostics.splice(0, diagnostics.length, ...remaining)
    renderDiagnostics()
  }

  return {
    showIdle(message = '打开 Boss 职位详情后，将自动分析当前岗位。') {
      setTitle(null)
      setMessage(message)
    },
    showLoading(job) {
      setTitle(job)
      setMessage('正在读取本地知识库并匹配…', 'status loading')
    },
    showResult(job, result) {
      setTitle(job)
      body.replaceChildren()

      const scores = document.createElement('div')
      scores.className = 'scores'
      for (const [label, value] of [['岗位适合度', result.suitabilityScore], ['定制可信度', result.customizationConfidence]] as const) {
        const item = document.createElement('div')
        item.className = 'score'
        const caption = document.createElement('span')
        caption.textContent = label
        const number = document.createElement('strong')
        number.textContent = String(value)
        item.append(caption, number)
        scores.append(item)
      }
      body.append(scores)

      const strategy = document.createElement('div')
      strategy.className = 'strategy'
      const strategyCaption = document.createElement('span')
      strategyCaption.textContent = '建议材料策略'
      const strategyValue = document.createElement('strong')
      strategyValue.textContent = strategyLabels[result.decision.materialStrategy]
      strategy.append(strategyCaption, strategyValue)
      body.append(strategy)

      if (result.analysis.riskRequirements.length) {
        const risks = document.createElement('section')
        risks.className = 'risks'
        const heading = document.createElement('h3')
        heading.textContent = '风险提示'
        risks.append(heading)
        for (const requirement of result.analysis.riskRequirements) {
          const risk = document.createElement('p')
          risk.className = 'risk'
          risk.textContent = `${requirement.explanation}：${requirement.evidence.text}`
          risks.append(risk)
        }
        body.append(risks)
      }

      const evidence = document.createElement('section')
      evidence.className = 'evidence'
      const heading = document.createElement('h3')
      heading.textContent = '本地知识库证据'
      evidence.append(heading)
      if (!result.evidence.length) {
        const empty = document.createElement('p')
        empty.className = 'status'
        empty.textContent = '没有找到可用证据，将使用默认材料。'
        evidence.append(empty)
      }
      for (const item of result.evidence.slice(0, 3)) {
        const article = document.createElement('article')
        const header = document.createElement('header')
        const name = document.createElement('strong')
        name.textContent = item.sourceName
        const score = document.createElement('span')
        score.textContent = `匹配 ${(item.score * 100).toFixed(1)}%`
        header.append(name, score)
        const content = document.createElement('p')
        content.textContent = item.content
        article.append(header, content)
        evidence.append(article)
      }
      body.append(evidence)
    },
    showError(job, message) {
      setTitle(job)
      setMessage(message, 'status error')
      reportDiagnostic({ level: 'error', code: 'analysis-error', message })
    },
    reportDiagnostic,
    clearDiagnostic,
    destroy() { host.remove() },
  }
}
