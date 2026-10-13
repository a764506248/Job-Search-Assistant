import { computed, ref } from 'vue'
import { api } from '../services/api'
import type { AutomationRun, DeliveryRecord, StoredJob } from '../types'

/** 单日指标行 */
export interface DailyMetric {
  date: string
  label: string
  captured: number
  delivered: number
  failed: number
}

export interface MetricsSummary {
  totalJobs: number
  totalCompanies: number
  capturedToday: number
  capturedYesterday: number
  deliveredTotal: number
  deliveredToday: number
  failedTotal: number
  successRate: number
  communicated: number
  interview: number
  deliverySource: 'records' | 'runs' | 'none'
}

function dayKey(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function dayLabel(date: string) {
  const [, month, day] = date.split('-')
  return `${Number(month)}/${Number(day)}`
}

/** 生成从 today 往前数 days 天的日期键（含今天），按时间升序 */
export function recentDayKeys(days: number) {
  const keys: string[] = []
  const today = new Date()
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset)
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    keys.push(`${date.getFullYear()}-${month}-${day}`)
  }
  return keys
}

export function isSuccessStatus(status: string) {
  return status === 'delivered' || status === 'greeting_sent'
}

export function isFailureStatus(status: string) {
  return status === 'failed' || status === 'fatal_limit'
}

/** 分页拉取全部职位快照（/v1/jobs 单页上限 100） */
export async function fetchAllJobs(maxPages = 50): Promise<StoredJob[]> {
  const first = await api.jobs({ page: 1, pageSize: 100 })
  const jobs = [...first.items]
  const pages = Math.min(first.totalPages, maxPages)
  for (let page = 2; page <= pages; page += 1) {
    const next = await api.jobs({ page, pageSize: 100 })
    jobs.push(...next.items)
  }
  return jobs
}

export function useMetrics() {
  const loading = ref(false)
  const error = ref('')
  const jobs = ref<StoredJob[]>([])
  const deliveries = ref<DeliveryRecord[]>([])
  const runs = ref<AutomationRun[]>([])
  const jobTotal = ref(0)

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const [jobList, deliveryList, runList] = await Promise.all([
        fetchAllJobs(),
        api.deliveries().catch(() => ({ total: 0, items: [] as DeliveryRecord[] })),
        api.automationRuns().catch(() => ({ items: [] as AutomationRun[] })),
      ])
      jobs.value = jobList
      deliveries.value = deliveryList.items
      runs.value = runList.items
      jobTotal.value = jobList.length
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '指标加载失败'
    } finally {
      loading.value = false
    }
  }

  /** 投递按天统计：优先用投递明细，没有明细时退回自动化运行的成功/失败计数 */
  const deliveryByDay = computed(() => {
    const map = new Map<string, { delivered: number; failed: number }>()
    if (deliveries.value.length) {
      for (const record of deliveries.value) {
        const key = dayKey(record.appliedAt)
        if (!key) continue
        const bucket = map.get(key) || { delivered: 0, failed: 0 }
        if (isSuccessStatus(record.status)) bucket.delivered += 1
        else if (isFailureStatus(record.status)) bucket.failed += 1
        map.set(key, bucket)
      }
      return { map, source: 'records' as const }
    }
    if (runs.value.length) {
      for (const run of runs.value) {
        const key = dayKey(run.finishedAt || run.startedAt || run.createdAt)
        if (!key) continue
        const bucket = map.get(key) || { delivered: 0, failed: 0 }
        bucket.delivered += run.successCount || 0
        bucket.failed += run.failureCount || 0
        map.set(key, bucket)
      }
      return { map, source: 'runs' as const }
    }
    return { map, source: 'none' as const }
  })

  const captureByDay = computed(() => {
    const map = new Map<string, number>()
    for (const job of jobs.value) {
      const key = dayKey(job.capturedAt)
      if (!key) continue
      map.set(key, (map.get(key) || 0) + 1)
    }
    return map
  })

  const summary = computed<MetricsSummary>(() => {
    const today = dayKey(new Date().toISOString())
    const yesterday = recentDayKeys(2)[0]
    const deliveredTotal = deliveries.value.length
      ? deliveries.value.filter((record) => isSuccessStatus(record.status)).length
      : runs.value.reduce((total, run) => total + (run.successCount || 0), 0)
    const failedTotal = deliveries.value.length
      ? deliveries.value.filter((record) => isFailureStatus(record.status)).length
      : runs.value.reduce((total, run) => total + (run.failureCount || 0), 0)
    const todayBucket = deliveryByDay.value.map.get(today) || { delivered: 0, failed: 0 }
    const attempted = deliveredTotal + failedTotal
    return {
      totalJobs: jobTotal.value,
      totalCompanies: new Set(jobs.value.map((job) => job.companyName)).size,
      capturedToday: captureByDay.value.get(today) || 0,
      capturedYesterday: captureByDay.value.get(yesterday) || 0,
      deliveredTotal,
      deliveredToday: todayBucket.delivered,
      failedTotal,
      successRate: attempted ? Math.round((deliveredTotal / attempted) * 100) : 0,
      communicated: jobs.value.filter((job) => job.hasCommunicated).length,
      interview: jobs.value.filter((job) => job.hasInterview).length,
      deliverySource: deliveryByDay.value.source,
    }
  })

  function daily(days: number): DailyMetric[] {
    return recentDayKeys(days).map((date) => {
      const bucket = deliveryByDay.value.map.get(date) || { delivered: 0, failed: 0 }
      return {
        date,
        label: dayLabel(date),
        captured: captureByDay.value.get(date) || 0,
        delivered: bucket.delivered,
        failed: bucket.failed,
      }
    })
  }

  /** 投递结果分布 */
  const deliveryStatusBreakdown = computed(() => {
    const labels: Record<string, string> = {
      delivered: '投递成功',
      greeting_sent: '已发招呼',
      failed: '投递失败',
      skipped: '已跳过',
      blocked: '被规则拦截',
      fatal_limit: '触发上限',
    }
    const counters = new Map<string, number>()
    for (const record of deliveries.value) {
      counters.set(record.status, (counters.get(record.status) || 0) + 1)
    }
    return Object.entries(labels)
      .map(([status, label]) => ({ status, label, count: counters.get(status) || 0 }))
      .filter((item) => item.count > 0)
  })

  /** 按公司统计投递量（取前 N） */
  const topCompanies = computed(() => {
    const counters = new Map<string, number>()
    if (deliveries.value.length) {
      for (const record of deliveries.value) {
        counters.set(record.companyName, (counters.get(record.companyName) || 0) + 1)
      }
    } else {
      for (const job of jobs.value) {
        counters.set(job.companyName, (counters.get(job.companyName) || 0) + 1)
      }
    }
    return [...counters.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8)
  })

  const recentDeliveries = computed(() =>
    [...deliveries.value]
      .sort((a, b) => new Date(b.appliedAt).getTime() - new Date(a.appliedAt).getTime())
      .slice(0, 5),
  )

  return {
    loading,
    error,
    jobs,
    deliveries,
    runs,
    summary,
    daily,
    deliveryStatusBreakdown,
    topCompanies,
    recentDeliveries,
    load,
  }
}

export const deliveryStatusText: Record<string, string> = {
  delivered: '投递成功',
  greeting_sent: '已发招呼',
  failed: '投递失败',
  skipped: '已跳过',
  blocked: '被拦截',
  fatal_limit: '触发上限',
}
