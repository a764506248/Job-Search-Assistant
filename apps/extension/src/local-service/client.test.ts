import { afterEach, describe, expect, it, vi } from 'vitest'
import { LocalServiceClient } from './client'

describe('LocalServiceClient', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends a captured job to the local FastAPI contract', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ jobs: [], inserted: 1, updated: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const input = {
      jobs: [{
        platform: 'boss' as const,
        platformJobId: 'job-1',
        url: 'https://www.zhipin.com/job_detail/job-1.html',
        title: '前端工程师',
        companyName: '示例公司',
        description: '负责业务开发',
        skills: ['Vue'],
        capturedAt: '2026-09-28T08:00:00.000Z',
        source: 'dom' as const,
      }],
    }

    await new LocalServiceClient('http://127.0.0.1:8765', 'local-token').captureJobs(input)

    expect(fetchMock).toHaveBeenCalledOnce()
    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    const [url, init] = call!
    expect(url).toBe('http://127.0.0.1:8765/v1/jobs/capture')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Headers).get('Content-Type')).toBe('application/json')
    expect((init?.headers as Headers).get('X-Local-Token')).toBe('local-token')
    expect(JSON.parse(init?.body as string)).toEqual(input)
  })

  it('checks health without sending the local token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', service: 'job-search-assistant-local' }), { status: 200 }),
    )

    await new LocalServiceClient('http://127.0.0.1:8765', 'secret').health()

    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    const headers = call![1]?.headers as Headers
    expect(headers.has('X-Local-Token')).toBe(false)
  })

  it('requests automatic hybrid matching for a job', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ suitabilityScore: 80, evidence: [] }), { status: 200 }),
    )

    await new LocalServiceClient('http://127.0.0.1:8765').matchJob({
      jobText: '负责 Python 与 RAG 开发',
      title: 'AI 应用开发工程师',
      skills: ['Python', 'RAG'],
    })

    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('http://127.0.0.1:8765/v1/jobs/match')
    expect(init?.method).toBe('POST')
  })
})
