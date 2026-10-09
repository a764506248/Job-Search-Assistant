<template>
  <section class="page-stack metrics-page">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">METRICS</p>
        <h2>数据指标</h2>
        <p class="muted">按天统计采集与投递数据，投递口径与「自动投递」实际结果一致。</p>
      </div>
      <div class="range-switch">
        <a-button
          v-for="option in ranges"
          :key="option"
          size="small"
          :type="range === option ? 'primary' : 'default'"
          @click="range = option"
        >近 {{ option }} 天</a-button>
      </div>
    </div>

    <div v-if="error" class="auth-error">{{ error }}</div>

    <div class="metric-grid metrics-summary">
      <article class="metric-card"><span>累计采集</span><strong>{{ summary.totalJobs }}</strong><small>覆盖 {{ summary.totalCompanies }} 家公司</small></article>
      <article class="metric-card"><span>累计投递</span><strong>{{ summary.deliveredTotal }}</strong><small>失败 {{ summary.failedTotal }} 次</small></article>
      <article class="metric-card"><span>投递成功率</span><strong>{{ summary.successRate }}%</strong><small>{{ sourceText }}</small></article>
      <article class="metric-card"><span>沟通 / 面试</span><strong>{{ summary.communicated }} / {{ summary.interview }}</strong><small>简历投出后的进展</small></article>
    </div>

    <section class="panel">
      <div class="panel-heading"><div><p class="eyebrow">DAILY</p><h2>每日明细</h2></div></div>
      <div class="table-panel">
        <table>
          <thead><tr><th>日期</th><th>新增采集</th><th>成功投递</th><th>投递失败</th><th>当日投递合计</th></tr></thead>
          <tbody>
            <tr v-for="day in rows" :key="day.date">
              <td>{{ day.date }}<span class="weekday"> {{ weekday(day.date) }}</span></td>
              <td>{{ day.captured }}</td>
              <td>{{ day.delivered }}</td>
              <td>{{ day.failed }}</td>
              <td>{{ day.delivered + day.failed }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td>合计</td>
              <td>{{ rangeTotals.captured }}</td>
              <td>{{ rangeTotals.delivered }}</td>
              <td>{{ rangeTotals.failed }}</td>
              <td>{{ rangeTotals.delivered + rangeTotals.failed }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <div class="metrics-split">
      <section class="panel">
        <div class="panel-heading"><div><p class="eyebrow">OUTCOME</p><h2>投递结果分布</h2></div></div>
        <div v-if="!deliveryStatusBreakdown.length" class="empty-state"><span class="empty-icon">▶</span><h3>暂无投递结果</h3><p>投递任务完成后会在这里按结果分类。</p></div>
        <ul v-else class="breakdown-list">
          <li v-for="item in deliveryStatusBreakdown" :key="item.status">
            <span class="breakdown-label">{{ item.label }}</span>
            <span class="breakdown-bar"><i :style="{ width: breakdownWidth(item.count) }"></i></span>
            <span class="breakdown-count">{{ item.count }}</span>
          </li>
        </ul>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="eyebrow">TOP</p><h2>{{ deliveries.length ? '投递最多的公司' : '采集最多的公司' }}</h2></div></div>
        <ul v-if="topCompanies.length" class="breakdown-list">
          <li v-for="item in topCompanies" :key="item.name">
            <span class="breakdown-label" :title="item.name">{{ item.name }}</span>
            <span class="breakdown-bar"><i :style="{ width: breakdownWidth(item.count) }"></i></span>
            <span class="breakdown-count">{{ item.count }}</span>
          </li>
        </ul>
        <div v-else class="empty-state"><span class="empty-icon">◇</span><h3>暂无数据</h3><p>采集职位后这里会显示公司分布。</p></div>
      </section>
    </div>

    <section class="panel metrics-recent-panel">
      <div class="panel-heading"><div><p class="eyebrow">RECENT</p><h2>最近投递明细</h2></div></div>
      <div v-if="!recent.length" class="empty-state"><span class="empty-icon">▶</span><h3>还没有投递记录</h3><p>投递明细会自动同步到指标页。</p></div>
      <div v-else class="table-panel">
        <table>
          <thead><tr><th>时间</th><th>职位</th><th>公司</th><th>结果</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="record in recent" :key="record.id">
              <td>{{ formatTime(record.appliedAt) }}</td>
              <td>{{ record.title }}</td>
              <td>{{ record.companyName }}</td>
              <td><span class="status-tag" :class="isSuccessStatus(record.status) ? 'is-active' : 'is-inactive'">{{ statusText(record.status) }}</span></td>
              <td>{{ record.reason || record.detail || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMetrics, isSuccessStatus, deliveryStatusText } from '../../composables/useMetrics'
import { useRefresh } from '../../composables/useRefresh'
import { formatTime } from '../../utils/format'

const ranges = [7, 14, 30]
const range = ref(7)

const { loading, error, deliveries, summary, daily, deliveryStatusBreakdown, topCompanies, recentDeliveries, load } = useMetrics()

const rows = computed(() => daily(range.value).slice().reverse())

const rangeTotals = computed(() => {
  const all = daily(range.value)
  return {
    captured: all.reduce((total, day) => total + day.captured, 0),
    delivered: all.reduce((total, day) => total + day.delivered, 0),
    failed: all.reduce((total, day) => total + day.failed, 0),
  }
})

const recent = computed(() => recentDeliveries.value)

const maxBreakdown = computed(() => Math.max(1, ...deliveryStatusBreakdown.value.map((item) => item.count), ...topCompanies.value.map((item) => item.count)))

function breakdownWidth(count: number) {
  return `${Math.round((count / maxBreakdown.value) * 100)}%`
}

function weekday(date: string) {
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(`${date}T00:00:00`).getDay()]
}

const sourceText = computed(() => {
  if (summary.value.deliverySource === 'records') return '按投递明细统计'
  if (summary.value.deliverySource === 'runs') return '按投递任务汇总统计'
  return '暂无投递数据'
})

function statusText(status: string) {
  return deliveryStatusText[status] || status
}

useRefresh(load)
</script>
