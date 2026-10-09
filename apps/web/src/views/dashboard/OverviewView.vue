<template>
  <div class="view active-view page-stack">
    <div class="intro-card">
      <div><span class="pill">本地优先</span><h2>你的求职数据，由你自己掌控</h2><p>扩展采集到的 Boss 职位会进入这里。项目库、简历和匹配规则都在本机统一管理。</p></div>
      <div class="privacy-stamp"><span>LOCAL</span><small>不上传产品服务器</small></div>
    </div>

    <div class="metric-grid" aria-label="数据概览">
      <article class="metric-card">
        <span>职位快照</span>
        <strong>{{ summary.totalJobs }}</strong>
        <small>累计 {{ summary.totalCompanies }} 家公司</small>
      </article>
      <article class="metric-card">
        <span>累计投递</span>
        <strong>{{ summary.deliveredTotal }}</strong>
        <small>失败 {{ summary.failedTotal }} · 成功率 {{ summary.successRate }}%</small>
      </article>
      <article class="metric-card">
        <span>今日投递</span>
        <strong>{{ summary.deliveredToday }}</strong>
        <small>今日采集 {{ summary.capturedToday }} · 昨日采集 {{ summary.capturedYesterday }}</small>
      </article>
      <article class="metric-card accent-card">
        <span>沟通进展</span>
        <strong>{{ summary.communicated }} / {{ summary.interview }}</strong>
        <small>已沟通 / 已约面</small>
      </article>
    </div>

    <section class="panel">
      <div class="panel-heading">
        <div><p class="eyebrow">LAST 7 DAYS</p><h2>近 7 天每日数据</h2></div>
        <a-button type="link" @click="router.push('/metrics')">查看指标 →</a-button>
      </div>
      <p class="trend-legend">
        <span><i class="dot dot-capture"></i>新增采集</span>
        <span><i class="dot dot-delivery"></i>成功投递</span>
      </p>
      <div class="trend-canvas">
        <div
          class="trend-chart"
          :class="{ 'is-flat': !weekHasData }"
          role="img"
          aria-label="近 7 天采集与投递趋势"
        >
          <div v-for="day in week" :key="day.date" class="trend-col">
            <div class="trend-bars">
              <span
                class="bar bar-capture"
                :style="{ height: barHeight(day.captured) }"
                :title="`${day.label} 采集 ${day.captured} 条`"
              ></span>
              <span
                class="bar bar-delivery"
                :style="{ height: barHeight(day.delivered) }"
                :title="`${day.label} 投递 ${day.delivered} 次（失败 ${day.failed}）`"
              ></span>
            </div>
            <div class="trend-values">
              <span :class="{ 'is-empty': !day.captured }">{{ day.captured }}</span>
              <span :class="{ 'is-empty': !day.delivered }">{{ day.delivered }}</span>
            </div>
            <span class="trend-label">{{ day.label }}</span>
          </div>
        </div>
        <p v-if="!weekHasData" class="trend-empty-hint">近 7 天还没有采集或投递记录</p>
      </div>
      <p class="trend-footnote">{{ sourceText }}</p>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="eyebrow">RECENT DELIVERIES</p><h2>最近投递</h2></div></div>
      <div v-if="loading" class="library-empty">正在读取投递数据…</div>
      <div v-else-if="!recentDeliveries.length" class="empty-state">
        <span class="empty-icon">▶</span>
        <h3>还没有投递记录</h3>
        <p>在「自动投递」里跑一次任务，投递结果会按天统计到这里。</p>
      </div>
      <div v-else class="job-list">
        <article v-for="record in recentDeliveries" :key="record.id" class="job-row">
          <div><h3>{{ record.title }}</h3><p>{{ record.companyName }}</p></div>
          <span class="status-tag" :class="isSuccessStatus(record.status) ? 'is-active' : 'is-inactive'">{{ statusText(record.status) }}</span>
          <time class="job-time">{{ formatTime(record.appliedAt) }}</time>
        </article>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="eyebrow">RECENT CAPTURES</p><h2>最近采集的职位</h2></div><a-button type="link" @click="router.push('/jobs')">查看全部 →</a-button></div>
      <div v-if="loading" class="library-empty">正在读取职位数据…</div>
      <div v-else-if="!jobs.length" class="empty-state"><span class="empty-icon">▤</span><h3>等待第一份 JD</h3><p>打开 Boss 职位详情页后，采集结果会出现在这里。</p></div>
      <div v-else class="job-list">
        <article v-for="job in jobs.slice(0, 5)" :key="job.id" class="job-row">
          <div><h3>{{ job.title }}</h3><p>{{ job.companyName }}</p></div>
          <span class="job-meta">{{ formatSalary(job.salaryText) }} · {{ job.location || '地点未识别' }}</span>
          <time class="job-time">{{ formatTime(job.capturedAt) }}</time>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMetrics, isSuccessStatus, deliveryStatusText } from '../../composables/useMetrics'
import { useRefresh } from '../../composables/useRefresh'
import { formatSalary, formatTime } from '../../utils/format'

const router = useRouter()
const { loading, jobs, summary, daily, recentDeliveries, load } = useMetrics()

const week = computed(() => daily(7))
const weekHasData = computed(() =>
  week.value.some((day) => day.captured || day.delivered || day.failed),
)
const maxValue = computed(() => Math.max(1, ...week.value.flatMap((day) => [day.captured, day.delivered])))

function barHeight(value: number) {
  if (!value) return '0%'
  return `${Math.max(6, Math.round((value / maxValue.value) * 100))}%`
}

const sourceText = computed(() => {
  if (summary.value.deliverySource === 'records') return '数据来源：投递明细记录'
  if (summary.value.deliverySource === 'runs') return '数据来源：投递任务汇总'
  return '暂无投递数据'
})

function statusText(status: string) {
  return deliveryStatusText[status] || status
}

useRefresh(load)
</script>
