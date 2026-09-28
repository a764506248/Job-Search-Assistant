import type { AutomaticJobMatchResponse, CapturedJob } from '@job-search-assistant/contracts'
import { afterEach, describe, expect, it } from 'vitest'
import { mountJobAnalysisPanel } from './job-analysis-panel'

const job: CapturedJob = {
  platform: 'boss',
  platformJobId: 'job-1',
  url: 'https://www.zhipin.com/job_detail/job-1.html',
  title: 'AI 应用开发工程师',
  companyName: '示例公司',
  description: '负责 Python 和 RAG 开发，985、211 优先',
  skills: ['Python', 'RAG'],
  capturedAt: '2026-09-28T08:00:00.000Z',
  source: 'dom',
}

const result: AutomaticJobMatchResponse = {
  analysis: {
    requirements: [],
    riskRequirements: [{
      category: 'elite_school',
      level: 'preferred',
      normalizedValue: '985|211',
      evidence: { text: '985、211 优先', start: 18, end: 28 },
      explanation: '文本将学校背景表述为优先条件',
    }],
    hasRiskSignals: true,
    parserVersion: 'jd-rule-parser-1',
  },
  suitabilityScore: 72,
  customizationConfidence: 68,
  decision: {
    materialStrategy: 'default',
    shouldDeliver: true,
    effectiveSuitabilityScore: 72,
    reasons: ['命中风险规则，使用默认简历和默认问候语'],
    ruleMatches: [],
  },
  evidence: [{
    sourceType: 'projects', sourceId: '1', sourceName: '企业知识库', chunkIndex: 0,
    content: '使用 Python 与 RAG 构建知识检索服务', score: 0.82, vectorScore: 0.8, keywordScore: 0.86,
  }],
  scoringVersion: 'local-hybrid-v1',
}

describe('job analysis panel', () => {
  afterEach(() => { document.body.innerHTML = ''; document.querySelector('#job-search-assistant-host')?.remove() })

  it('renders analysis inside an isolated shadow root', () => {
    const panel = mountJobAnalysisPanel(document)
    panel.showResult(job, result)

    const host = document.querySelector('#job-search-assistant-host')
    const text = host?.shadowRoot?.textContent ?? ''
    expect(host?.shadowRoot).toBeTruthy()
    expect(text).toContain('AI 应用开发工程师 · 示例公司')
    expect(text).toContain('岗位适合度')
    expect(text).toContain('72')
    expect(text).toContain('默认简历 + 默认问候语')
    expect(text).toContain('985、211 优先')
    expect(text).toContain('企业知识库')
    expect(document.body.textContent).not.toContain('岗位适合度')
  })

  it('renders loading and failure states', () => {
    const panel = mountJobAnalysisPanel(document)
    panel.showLoading(job)
    const shadow = document.querySelector('#job-search-assistant-host')?.shadowRoot
    expect(shadow?.textContent).toContain('正在读取本地知识库并匹配')

    panel.showError(job, '本地服务不可用')
    expect(shadow?.textContent).toContain('本地服务不可用')
  })
})
