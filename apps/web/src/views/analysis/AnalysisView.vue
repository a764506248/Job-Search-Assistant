<template>
  <div class="view active-view analysis-view">
    <section class="panel analysis-command">
      <div>
        <p class="eyebrow">JOB INSIGHT</p>
        <h2>分析当前职位</h2>
        <p>本地分析使用规则与知识库证据；AI 分析会调用已配置模型。两种方式都只读，不会投递或发送消息。</p>
      </div>
      <label class="analysis-job-picker">
        <span>选择职位</span>
        <select v-model.number="selectedJobId" :disabled="loadingJobs || !jobs.length">
          <option v-for="job in jobs" :key="job.id" :value="job.id">{{ job.title }} · {{ job.companyName }}</option>
        </select>
      </label>
      <div class="analysis-actions">
        <a-button :disabled="!selectedJob" :loading="analyzing === 'local'" @click="runAnalysis(false)">本地分析</a-button>
        <a-button type="primary" :disabled="!selectedJob" :loading="analyzing === 'ai'" @click="runAnalysis(true)">使用 AI 分析</a-button>
      </div>
    </section>

    <div v-if="loadingJobs" class="panel library-empty">正在读取职位快照…</div>
    <div v-else-if="!jobs.length" class="panel empty-state">
      <span class="empty-icon">◈</span><h3>还没有可分析的职位</h3><p>请先采集或手动添加职位快照。</p>
      <a-button type="primary" @click="router.push('/jobs')">前往职位快照</a-button>
    </div>

    <div v-else class="analysis-layout">
      <aside v-if="selectedJob" class="panel analysis-job-card">
        <div class="panel-heading"><div><p class="eyebrow">CURRENT JOB</p><h2>{{ selectedJob.title }}</h2></div></div>
        <dl>
          <div><dt>公司</dt><dd>{{ selectedJob.companyName }}</dd></div>
          <div><dt>薪资</dt><dd>{{ formatSalary(selectedJob.salaryText, '未识别') }}</dd></div>
          <div><dt>地点</dt><dd>{{ selectedJob.location || '未识别' }}</dd></div>
          <div><dt>要求</dt><dd>{{ [selectedJob.experience, selectedJob.education].filter(Boolean).join(' · ') || '未识别' }}</dd></div>
        </dl>
        <div v-if="selectedJob.skills?.length" class="tags"><span v-for="skill in selectedJob.skills" :key="skill" class="tag">{{ skill }}</span></div>
        <details class="analysis-jd"><summary>查看完整 JD</summary><pre>{{ selectedJob.description }}</pre></details>
      </aside>

      <div class="analysis-result-column">
        <section v-if="!insight" class="panel analysis-placeholder">
          <span>◈</span><h2>选择一种分析方式</h2><p>建议先查看本地分析；需要更完整的岗位解读、差距建议和面试准备时，再使用 AI 分析。</p>
        </section>

        <template v-else>
          <section class="panel analysis-summary">
            <div class="analysis-result-heading">
              <div><p class="eyebrow">{{ insight.mode === 'ai' ? 'AI ANALYSIS' : 'LOCAL ANALYSIS' }}</p><h2>{{ insight.mode === 'ai' ? 'AI 深度分析' : '本地规则分析' }}</h2></div>
              <span class="analysis-mode">{{ insight.mode === 'ai' ? `${insight.modelName} · ${insight.modelId}` : '本地规则 + 资料匹配' }}</span>
            </div>
            <p class="analysis-summary-text">{{ insight.summary }}</p>
            <div class="match-metrics">
              <div><span>岗位适合度</span><strong>{{ insight.match.suitabilityScore }}</strong></div>
              <div><span>定制可信度</span><strong>{{ insight.match.customizationConfidence }}</strong></div>
              <div><span>材料策略</span><strong>{{ strategyLabel(insight.match.decision.materialStrategy) }}</strong></div>
            </div>
          </section>

          <section class="analysis-grid">
            <article class="panel analysis-list is-strength"><h3>匹配优势</h3><ul v-if="insight.strengths.length"><li v-for="item in insight.strengths" :key="item">{{ item }}</li></ul><p v-else>暂未发现有充分证据支撑的匹配优势。</p></article>
            <article class="panel analysis-list is-gap"><h3>差距与风险</h3><ul v-if="insight.gaps.length"><li v-for="item in insight.gaps" :key="item">{{ item }}</li></ul><p v-else>暂未识别明显风险，仍建议人工核对 JD。</p></article>
            <article class="panel analysis-list"><h3>行动建议</h3><ul><li v-for="item in insight.recommendations" :key="item">{{ item }}</li></ul></article>
            <article class="panel analysis-list"><h3>面试准备</h3><ul><li v-for="item in insight.interviewQuestions" :key="item">{{ item }}</li></ul></article>
          </section>

          <section class="panel match-evidence">
            <h3>分析采用的知识库证据</h3>
            <article v-for="item in insight.match.evidence.slice(0, 6)" :key="`${item.sourceId}-${item.chunkIndex}`"><div><strong>{{ item.sourceName }}</strong><span>综合 {{ percent(item.score) }}</span></div><p>{{ item.content }}</p></article>
            <p v-if="!insight.match.evidence.length">暂无知识库证据。建议先完善个人档案、项目库和简历库后重新分析。</p>
          </section>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useRefresh } from '../../composables/useRefresh'
import { api } from '../../services/api'
import { formatSalary } from '../../utils/format'
import type { JobInsight, StoredJob } from '../../types'

const route = useRoute()
const router = useRouter()
const jobs = ref<StoredJob[]>([])
const selectedJobId = ref<number | null>(null)
const insight = ref<JobInsight | null>(null)
const loadingJobs = ref(false)
const analyzing = ref<'local' | 'ai' | null>(null)
const selectedJob = computed(() => jobs.value.find((job) => job.id === selectedJobId.value) || null)
const percent = (value: number) => `${(value * 100).toFixed(1)}%`
const strategyLabel = (value: string) => ({ custom: '定制材料', default: '默认材料', blocked: '暂不投递' } as Record<string, string>)[value] || value

async function load() {
  loadingJobs.value = true
  try {
    const result = await api.jobs({ page: 1, pageSize: 100 })
    jobs.value = result.items
    const requestedId = Number(route.query.jobId)
    selectedJobId.value = jobs.value.some((job) => job.id === requestedId) ? requestedId : (jobs.value[0]?.id ?? null)
  } catch (error) { message.error((error as Error).message) }
  finally { loadingJobs.value = false }
}

async function runAnalysis(useAi: boolean) {
  if (!selectedJobId.value) return
  analyzing.value = useAi ? 'ai' : 'local'
  try {
    insight.value = await api.analyzeJob(selectedJobId.value, useAi)
    message.success(useAi ? 'AI 分析完成' : '本地分析完成')
  } catch (error) { message.error((error as Error).message) }
  finally { analyzing.value = null }
}

watch(selectedJobId, (id, previous) => {
  if (id !== previous) insight.value = null
  if (id) void router.replace({ name: 'analysis', query: { jobId: id } })
})

useRefresh(load)
</script>
