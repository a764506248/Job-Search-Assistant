<template>
  <div class="view active-view">
    <div class="intro-card">
      <div><span class="pill">本地优先</span><h2>你的求职数据，由你自己掌控</h2><p>扩展采集到的 Boss 职位会进入这里。项目库、简历和匹配规则都在本机统一管理。</p></div>
      <div class="privacy-stamp"><span>LOCAL</span><small>不上传产品服务器</small></div>
    </div>
    <div class="metric-grid" aria-label="数据概览">
      <article class="metric-card"><span>职位快照</span><strong>{{ jobs.length }}</strong><small>已保存的 JD 版本</small></article>
      <article class="metric-card"><span>公司数量</span><strong>{{ companies }}</strong><small>当前资料涉及的公司</small></article>
      <article class="metric-card"><span>今日采集</span><strong>{{ todayCount }}</strong><small>今天新增的职位快照</small></article>
      <article class="metric-card accent-card"><span>知识库状态</span><strong>本地运行</strong><small>资料与向量保存在本机</small></article>
    </div>
    <section class="panel">
      <div class="panel-heading"><div><p class="eyebrow">RECENT CAPTURES</p><h2>最近采集的职位</h2></div><a-button type="link" @click="router.push('/jobs')">查看全部 →</a-button></div>
      <div v-if="loading" class="library-empty">正在读取职位数据…</div>
      <div v-else-if="!jobs.length" class="empty-state"><span class="empty-icon">▤</span><h3>等待第一份 JD</h3><p>打开 Boss 职位详情页后，采集结果会出现在这里。</p></div>
      <div v-else class="job-list">
        <article v-for="job in jobs.slice(0, 5)" :key="job.id" class="job-row">
          <div><h3>{{ job.title }}</h3><p>{{ job.companyName }}</p></div>
          <span class="job-meta">{{ job.salaryText || '薪资未识别' }} · {{ job.location || '地点未识别' }}</span>
          <time class="job-time">{{ formatTime(job.capturedAt) }}</time>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import { formatTime } from '../../utils/format'
import type { StoredJob } from '../../types'

const router = useRouter()
const jobs = ref<StoredJob[]>([])
const loading = ref(false)
const companies = computed(() => new Set(jobs.value.map((job) => job.companyName)).size)
const todayCount = computed(() => jobs.value.filter((job) => new Date(job.capturedAt).toDateString() === new Date().toDateString()).length)

async function load() {
  loading.value = true
  try { jobs.value = (await api.jobs()).items }
  catch (error) { message.error((error as Error).message) }
  finally { loading.value = false }
}

useRefresh(load)
</script>
