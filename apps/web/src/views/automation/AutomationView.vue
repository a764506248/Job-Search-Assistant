<template>
  <div class="view active-view automation-view">
    <section class="automation-command panel">
      <div><p class="eyebrow">ONE-CLICK AUTOMATION</p><h2>自动投递任务</h2><p>启动一次，系统会自动完成扩展采集和本地分析；准备流程只在企业清单确认处暂停，确认后自动进入投递。</p></div>
      <label>每日目标<input v-model.number="targetCount" type="number" min="1" max="500" /></label>
      <label>候选采集上限<input v-model.number="candidateLimit" type="number" :min="targetCount" max="500" /></label>
      <a-button type="primary" :disabled="launchDisabled" :loading="creating" @click="createRun">{{ launchButtonText }}</a-button>
    </section>
    <section class="automation-collection-settings panel" aria-label="本次采集筛选">
      <header>
        <div><strong>本次采集筛选</strong><span>只写入新任务快照，不修改个人档案中的默认设置</span></div>
        <span>岗位间隔 {{ collectionIntervalSeconds }} 秒</span>
      </header>
      <div class="automation-filter-grid">
        <label class="wide">搜索关键词<input v-model="searchKeywordsInput" placeholder="留空沿用个人档案；多个关键词用逗号分隔" /></label>
        <label>城市<select v-model="collectionCityCode"><option value="">沿用个人档案</option><option value="100010000">全国</option><option value="101010100">北京</option><option value="101020100">上海</option><option value="101280100">广州</option><option value="101280600">深圳</option><option value="101210100">杭州</option><option value="101270100">成都</option></select></label>
        <label>求职类型<select v-model="collectionFilters.jobType"><option value="">不限</option><option value="1901">全职</option><option value="1902">实习</option><option value="1903">兼职</option></select></label>
        <label>薪资待遇<select v-model="collectionFilters.salary"><option value="">不限</option><option value="402">3K 以下</option><option value="403">3–5K</option><option value="404">5–10K</option><option value="405">10–20K</option><option value="406">20–50K</option><option value="407">50K 以上</option></select></label>
        <label>工作经验<select v-model="collectionFilters.experience"><option value="">不限</option><option value="102">在校/应届</option><option value="103">1年以内</option><option value="104">1–3年</option><option value="105">3–5年</option><option value="106">5–10年</option><option value="107">10年以上</option></select></label>
        <label>学历要求<select v-model="collectionFilters.degree"><option value="">不限</option><option value="202">初中及以下</option><option value="203">中专/中技</option><option value="204">高中</option><option value="205">大专</option><option value="206">本科</option><option value="207">硕士</option><option value="208">博士</option></select></label>
        <label>公司规模<select v-model="collectionFilters.scale"><option value="">不限</option><option value="302">0–20人</option><option value="303">20–99人</option><option value="304">100–499人</option><option value="305">500–999人</option><option value="306">1000–9999人</option><option value="307">10000人以上</option></select></label>
        <label>公司行业编码<input v-model="collectionFilters.industry" inputmode="numeric" placeholder="可选；多个编码用逗号分隔" /></label>
        <label>岗位采集间隔（秒）<input v-model.number="collectionIntervalSeconds" type="number" min="0" max="30" step="0.5" /></label>
      </div>
      <p>扩展会把筛选条件写入 BOSS 搜索地址；每次打开并读取一个岗位后，按这里设置的间隔再处理下一个岗位。建议设置 2–5 秒。</p>
    </section>
    <section class="automation-pipeline panel" aria-label="自动投递流程">
      <template v-for="(stage, index) in pipelineStages" :key="stage.id">
        <div class="automation-pipeline-stage" :class="pipelineStageClass(stage.id)">
          <span class="automation-pipeline-index">{{ stage.id }}</span>
          <span class="automation-pipeline-copy"><strong>{{ stage.title }}</strong><small>{{ stage.description }}</small></span>
        </div>
        <span v-if="index < pipelineStages.length - 1" class="automation-pipeline-arrow" aria-hidden="true">→</span>
      </template>
    </section>
    <section class="automation-readiness panel">
      <div :class="{ ready: runnerReady }"><strong>执行器</strong><span>{{ runnerReady ? 'Docker 内置执行器在线' : '未在线，请重新启动 Docker 服务' }}</span></div>
      <div :class="{ ready: browserReady }"><strong>浏览器扩展</strong><span>{{ browserStatusText }}</span></div>
      <div :class="{ ready: setupReady }"><strong>启动检查</strong><span>{{ setupStatusText }}</span></div>
    </section>
    <div class="automation-layout">
      <section class="panel automation-runs">
        <div class="panel-heading"><h2>任务记录</h2><a-button @click="load">刷新</a-button></div>
        <div v-if="!runs.length" class="library-empty">还没有自动投递任务。</div>
        <article v-for="run in runs" :key="run.id" :class="{ selected: selected?.id === run.id }" @click="selectRun(run)">
          <div><strong>#{{ run.id }} · {{ runStatusName(run) }}</strong><span>计划 {{ plannedCount(run) }} · 目标 {{ run.targetCount }} · 成功 {{ run.successCount }} · 失败 {{ run.failureCount }}</span><span>{{ run.runnerId ? `执行器 ${run.runnerId} · 心跳 ${run.heartbeatAt ? formatTime(run.heartbeatAt) : '等待中'}` : run.status === 'draft' ? collectionSummary(run) : '尚未被执行器认领' }}</span><span v-if="collectionCount(run) > 0 || collectionExistingExcludedCount(run) > 0">{{ collectionResultSummary(run) }}</span></div>
          <div class="automation-actions" @click.stop>
            <a-button v-if="run.status === 'interrupted'" size="small" @click="control(run, 'start')">重新启动</a-button>
            <span v-if="isRetryable(run)" class="automation-retry-action"><a-button size="small" type="primary" :loading="retryingRunId === run.id" @click="retryRun(run)">投递重试</a-button></span>
            <a-button v-if="run.status === 'running'" size="small" @click="control(run, 'pause')">暂停</a-button>
            <a-button v-if="run.status === 'paused'" size="small" @click="control(run, 'resume')">继续</a-button>
            <a-button v-if="['running','paused'].includes(run.status)" size="small" danger @click="control(run, 'stop')">停止</a-button>
          </div>
        </article>
      </section>
      <section class="panel automation-events">
        <div class="panel-heading">
          <h2>{{ automationPanelTitle }}</h2>
          <div class="automation-event-controls">
            <span>{{ selected ? `任务 #${selected.id}` : '请选择任务' }}</span>
            <span v-if="selected && isRetryable(selected)" class="automation-retry-action"><a-button size="small" type="primary" :loading="retryingRunId === selected.id" @click="retryRun(selected)">投递重试</a-button></span>
            <a-button v-if="selected?.status === 'running'" size="small" @click="control(selected, 'pause')">暂停投递</a-button>
            <a-button v-if="selected?.status === 'paused'" size="small" type="primary" @click="control(selected, 'resume')">继续投递</a-button>
            <a-button v-if="selected && ['running','paused'].includes(selected.status)" size="small" danger @click="control(selected, 'stop')">停止</a-button>
          </div>
        </div>
        <div v-if="selected?.status === 'draft'" class="automation-plan">
          <div v-if="collectionStatus === 'collecting'" class="library-empty">
            <strong>{{ collectionPhaseTitle }}</strong>
            <p>{{ collectionProgressText }}</p>
            <div class="automation-activity" role="status" aria-live="polite">
              <i aria-hidden="true"></i>
              <span>已用时 {{ collectionElapsedText }}</span>
              <span v-if="!isAnalyzing">分批采集，每批最长约 30 秒</span>
              <span v-else>分析结果会逐条更新</span>
            </div>
            <div class="automation-progress-metrics">
              <span>已采集 {{ collection?.collectedCount || 0 }}</span>
              <span>已分析 {{ collection?.analyzedCount || 0 }}</span>
              <span>通过 {{ collection?.approvedCount || 0 }}</span>
              <span v-if="collection?.existingExcludedCount">本地去重 {{ collection.existingExcludedCount }}</span>
            </div>
          </div>
          <div v-else-if="isNoMatches || collectionStatus === 'failed'" :class="isNoMatches ? 'automation-no-matches' : 'library-empty'">
            <template v-if="isNoMatches">
              <div class="automation-no-matches-heading">
                <div>
                  <strong>{{ collection?.message || '采集与分析完成，暂无符合规则的岗位' }}</strong>
                  <p>新职位会完成本地规则判断；本地已有岗位会在扩展打开详情前直接跳过，不再重复采集。你可以调整关键词、候选上限或规则后重新采集。</p>
                </div>
                <a-button :disabled="!browserReady" :loading="collectingRunId === selected.id" @click="collectSelectedRun">重新采集</a-button>
              </div>
              <div class="automation-result-metrics" aria-label="采集分析统计">
                <div><strong>{{ collectionMetrics.collected }}</strong><span>已采集</span></div>
                <div><strong>{{ collectionMetrics.analyzed }}</strong><span>已分析</span></div>
                <div><strong>{{ collectionMetrics.approved }}</strong><span>通过</span></div>
                <div><strong>{{ collectionMetrics.rejected }}</strong><span>未通过</span></div>
                <div v-if="collection?.existingExcludedCount"><strong>{{ collection.existingExcludedCount }}</strong><span>本地去重</span></div>
              </div>
              <section v-if="reviewedJobs.length" class="automation-review-results" aria-label="岗位判断明细">
                <div class="automation-review-heading"><strong>岗位判断明细</strong><span>共 {{ reviewedJobs.length }} 个</span></div>
                <article v-for="job in reviewedJobs" :key="`${job.snapshotId}-${job.jobId}`" class="automation-reviewed-job">
                  <header>
                    <div><strong>{{ job.title || '未知岗位' }}</strong><span>{{ job.companyName || '未知企业' }}</span></div>
                    <em :class="`outcome-${job.outcome}`">{{ reviewOutcomeName(job.outcome) }}</em>
                  </header>
                  <p v-if="job.salaryText || job.location || job.suitabilityScore != null" class="automation-reviewed-meta">
                    <span v-if="job.salaryText">{{ formatSalary(job.salaryText) }}</span>
                    <span v-if="job.location">{{ job.location }}</span>
                    <span v-if="job.suitabilityScore != null">适合度 {{ job.suitabilityScore }}</span>
                  </p>
                  <ul><li v-for="(reason, index) in reviewReasons(job)" :key="`${job.jobId}-${index}`">{{ reason }}</li></ul>
                </article>
              </section>
              <p v-else class="automation-review-unavailable">该历史任务未保存逐岗位分析明细，统计结果仍可正常查看。</p>
            </template>
            <template v-else>
              <strong>职位采集失败</strong>
              <p>{{ collectionError }}</p>
              <a-button type="primary" :disabled="!browserReady" :loading="collectingRunId === selected.id" @click="collectSelectedRun">重新采集</a-button>
            </template>
          </div>
          <div v-else-if="collectionStatus !== 'ready'" class="library-empty">
            <strong>自动流程正在排队</strong>
            <p>{{ browserReady ? '系统会自动调用 Chrome 扩展采集职位，随后直接进入本地分析，无需再次点击。' : '等待 Chrome 扩展恢复连接；连接后页面会自动续跑。' }}</p>
          </div>
          <template v-else>
            <div v-if="plannedJobs.length" class="automation-plan-toolbar">
              <label><input type="checkbox" :checked="allJobsSelected" @change="toggleAllJobs" /> 全选当前计划</label>
              <span>已选 {{ selectedJobIds.length }} / {{ plannedJobs.length }} 个岗位 · {{ selectedCompanyCount }} 家企业</span>
            </div>
            <div v-if="!plannedJobs.length" class="library-empty">
              <strong>本次没有生成可投企业</strong>
              <p>扩展已完成采集，但没有岗位通过本地匹配规则。请调整关键词或规则后启动新的自动流程。</p>
            </div>
            <div v-else class="automation-plan-list">
              <label v-for="job in plannedJobs" :key="job.jobId" class="automation-plan-job" :class="{ chosen: selectedJobIds.includes(job.jobId) }">
                <input type="checkbox" :checked="selectedJobIds.includes(job.jobId)" @change="toggleJob(job.jobId)" />
                <span class="automation-plan-job-copy">
                  <strong>{{ job.companyName || '未知企业' }}</strong>
                  <b>{{ job.title || '未知岗位' }}</b>
                  <small v-if="job.salaryText || job.location">{{ [job.salaryText ? formatSalary(job.salaryText) : undefined, job.location].filter(Boolean).join(' · ') }}</small>
                  <em>{{ job.greeting || '未生成问候语' }}</em>
                </span>
              </label>
            </div>
            <footer v-if="plannedJobs.length">
              <p>只有勾选的企业岗位会写入最终计划。确认后执行器才会认领任务并操作浏览器。</p>
              <a-button type="primary" :disabled="!selectedJobIds.length" :loading="starting" @click="confirmAndStart">确认企业并开始投递（{{ selectedJobIds.length }}）</a-button>
            </footer>
          </template>
        </div>
        <template v-else>
        <section v-if="collectionMetrics.collected > 0" class="automation-collection-history" aria-label="本次任务采集分析结果">
          <div class="automation-collection-history-heading">
            <div><strong>采集分析结果</strong><p>这些数据已保存到本地；投递阶段不会覆盖采集结果。</p></div>
            <span>扩展 v{{ browser?.extensionVersion || '-' }}</span>
          </div>
          <div class="automation-result-metrics" aria-label="采集分析统计">
            <div><strong>{{ collectionMetrics.collected }}</strong><span>已采集</span></div>
            <div><strong>{{ collectionMetrics.analyzed }}</strong><span>已分析</span></div>
            <div><strong>{{ collectionMetrics.approved }}</strong><span>通过</span></div>
            <div><strong>{{ collectionMetrics.rejected }}</strong><span>未通过</span></div>
          </div>
          <details v-if="reviewedJobs.length" class="automation-review-details">
            <summary>查看 {{ reviewedJobs.length }} 个岗位的识别与规则判断</summary>
            <section class="automation-review-results" aria-label="岗位判断明细">
              <article v-for="job in reviewedJobs" :key="`${job.snapshotId}-${job.jobId}`" class="automation-reviewed-job">
                <header>
                  <div><strong>{{ job.title || '未知岗位' }}</strong><span>{{ job.companyName || '未知企业' }}</span></div>
                  <em :class="`outcome-${job.outcome}`">{{ reviewOutcomeName(job.outcome) }}</em>
                </header>
                <p v-if="job.salaryText || job.location || job.suitabilityScore != null" class="automation-reviewed-meta">
                  <span v-if="job.salaryText">{{ formatSalary(job.salaryText) }}</span>
                  <span v-if="job.location">{{ job.location }}</span>
                  <span v-if="job.suitabilityScore != null">适合度 {{ job.suitabilityScore }}</span>
                </p>
                <ul><li v-for="(reason, index) in reviewReasons(job)" :key="`${job.jobId}-${index}`">{{ reason }}</li></ul>
              </article>
            </section>
          </details>
        </section>
        <div v-if="selected?.stopReason" class="automation-blocker" :class="{ neutral: !isErrorStatus(selected.status) }">{{ reasonText(selected.stopReason) }}</div>
        <div v-if="report" class="automation-report-summary">
          <strong>投递结果</strong>：成功 {{ report.run.successCount }} · 失败 {{ report.run.failureCount }}
          <span>浏览器动作：成功 {{ actionSuccessCount }} · 失败 {{ actionFailureCount }}</span>
        </div>
        <div v-if="!events.length" class="library-empty">暂无事件。</div>
        <ol v-else><li v-for="event in events" :key="event.id"><span>#{{ event.sequence }}</span><strong>{{ eventName(event.eventType) }}</strong><time>{{ formatTime(event.createdAt) }}</time><p>{{ eventText(event) }}</p></li></ol>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import { formatSalary, formatTime } from '../../utils/format'
import type { AutomationCollectionFilters, AutomationCollectionState, AutomationCollectionStatus, AutomationEvent, AutomationReport, AutomationReviewedJob, AutomationReviewOutcome, AutomationRun, BrowserProtocolStatus, PlannedAutomationJob, SetupStatus } from '../../types'

const targetCount = ref(20)
const candidateLimit = ref(100)
const searchKeywordsInput = ref('')
const collectionCityCode = ref('')
const collectionIntervalSeconds = ref(2)
const collectionFilters = ref<AutomationCollectionFilters>({
  jobType: '',
  salary: '',
  experience: '',
  degree: '',
  industry: '',
  scale: '',
})
const creating = ref(false)
const collectingRunId = ref<number>()
const starting = ref(false)
const retryingRunId = ref<number>()
const runs = ref<AutomationRun[]>([])
const selected = ref<AutomationRun>()
const events = ref<AutomationEvent[]>([])
const report = ref<AutomationReport>()
const setup = ref<SetupStatus>()
const browser = ref<BrowserProtocolStatus>()
const selectedJobIds = ref<string[]>([])
const selectionRunId = ref<number>()
const nowMs = ref(Date.now())
const recoveryStates = new Map<number, { attempts: number; nextAttemptAt: number; observedUpdatedAt: string }>()
let stream: EventSource | undefined
let refreshTimer: ReturnType<typeof setInterval> | undefined
let elapsedTimer: ReturnType<typeof setInterval> | undefined

const COLLECTION_RECOVERY_MAX_ATTEMPTS = 4
const COLLECTION_RECOVERY_BASE_DELAY_MS = 5_000
const COLLECTION_STALE_AFTER_MS = 35_000

const names: Record<string, string> = { draft: '待启动', validating: '校验中', ready: '已就绪', running: '运行中', paused: '已暂停', stopping: '停止中', interrupted: '已中断', completed: '已完成', failed: '失败', blocked: '被阻止', cancelled: '已取消' }
const eventNames: Record<string, string> = { 'run-created': '任务已创建', 'retry-created': '投递重试已创建', 'collection-queued': '自动流程已排队', 'collection-started': '开始采集职位', 'collection-stage-changed': '自动流程阶段变化', 'collection-keyword': '正在采集关键词', 'collection-batch-finished': '采集批次完成', 'analysis-started': '开始本地分析', 'analysis-finished': '本地分析完成', 'collection-finished': '职位采集完成', 'collection-failed': '职位采集失败', 'plan-confirmed': '投递清单已确认', 'status-changed': '状态变化', 'status-corrected': '状态已修正', 'runner-awaiting-host': '等待执行器', 'runner-claimed': '执行器已认领', 'job-finished': '岗位处理完成', 'action-claimed': '浏览器动作开始', 'action-finished': '浏览器动作结束' }
const reviewOutcomeNames: Record<AutomationReviewOutcome, string> = {
  approved: '符合规则',
  rule_rejected: '规则未通过',
  duplicate: '重复岗位',
  material_error: '材料生成失败',
  analysis_error: '分析失败',
}
const pipelineStages = [
  { id: 1, title: '扩展采集', description: '搜索并读取职位' },
  { id: 2, title: '本地分析', description: '匹配规则与生成问候语' },
  { id: 3, title: '确认企业', description: '任务启动安全门' },
  { id: 4, title: '自动投递', description: '执行器按确认清单处理' },
] as const
const statusName = (status: string) => names[status] || status
const eventName = (event: string) => eventNames[event] || event
const runnerReady = computed(() => setup.value?.checks.some(item => item.key === 'automation-runner' && item.status === 'ready') ?? false)
const browserReady = computed(() => browser.value?.connected === true && extensionVersionAtLeast(browser.value.extensionVersion, [0, 4, 11]))
const blockingSetupChecks = computed(() => setup.value?.checks.filter(item => item.blocking
  && item.status !== 'ready'
  && !(item.key === 'boss-login' && browserReady.value)) ?? [])
const setupReady = computed(() => setup.value !== undefined && blockingSetupChecks.value.length === 0)
const setupStatusText = computed(() => {
  if (!setup.value) return '正在检查启动条件'
  if (setupReady.value) {
    const loginPending = setup.value.checks.some(item => item.key === 'boss-login' && item.status !== 'ready')
    return loginPending ? '可启动；BOSS 登录将在采集前自动确认' : '全部通过'
  }
  return `请先处理：${blockingSetupChecks.value.map(item => item.label).join('、')}`
})
const browserStatusText = computed(() => {
  if (!browser.value?.connected) return '未连接，请前往安装向导重新配对'
  if (!browserReady.value) return `已连接 v${browser.value.extensionVersion || '-'}，请重新加载 v0.4.11 或更高版本`
  return `已连接 · v${browser.value.extensionVersion}`
})
const actionSuccessCount = computed(() => report.value?.actions.filter(item => item.status === 'succeeded').length ?? 0)
const actionFailureCount = computed(() => report.value?.actions.filter(item => item.status === 'failed').length ?? 0)
const collectionFor = (run?: AutomationRun): AutomationCollectionState | undefined => {
  const value = run?.configSnapshot.collection
  return value && typeof value === 'object' && !Array.isArray(value) ? value as AutomationCollectionState : undefined
}
const collection = computed(() => collectionFor(selected.value))
const collectionStatus = computed<AutomationCollectionStatus>(() => collection.value?.status || 'pending')
const collectionPhase = computed(() => collection.value?.phase || (collectionStatus.value === 'ready' ? 'awaiting_confirmation' : collectionStatus.value))
const isAnalyzing = computed(() => collectionPhase.value === 'analyzing' || (collection.value?.analyzedCount || 0) > 0)
const isNoMatchesState = (state?: AutomationCollectionState) => state?.status === 'no_matches'
  || (state?.status === 'failed' && (state.collectedCount ?? 0) > 0)
const isNoMatches = computed(() => isNoMatchesState(collection.value))
const collectionError = computed(() => localizedCollectionError(collection.value?.message || collection.value?.reason || collection.value?.error))
const plannedJobs = computed<PlannedAutomationJob[]>(() => Array.isArray(selected.value?.configSnapshot.plannedJobs) ? selected.value!.configSnapshot.plannedJobs : [])
const reviewedJobs = computed<AutomationReviewedJob[]>(() => Array.isArray(collection.value?.reviewedJobs) ? collection.value.reviewedJobs : [])
const collectionMetrics = computed(() => {
  const collected = collection.value?.collectedCount ?? 0
  const analyzed = collection.value?.analyzedCount ?? (isNoMatches.value ? collected : 0)
  const approved = collection.value?.approvedCount ?? plannedJobs.value.length
  const rejected = collection.value?.rejectedCount ?? Math.max(0, analyzed - approved)
  return { collected, analyzed, approved, rejected }
})
const allJobsSelected = computed(() => plannedJobs.value.length > 0 && selectedJobIds.value.length === plannedJobs.value.length)
const selectedCompanyCount = computed(() => new Set(plannedJobs.value.filter(job => selectedJobIds.value.includes(job.jobId)).map(job => job.companyName)).size)
const runUpdatedAge = (run: AutomationRun) => Date.now() - Date.parse(run.updatedAt || run.createdAt)
const activePipelineRun = computed(() => runs.value.find(run => run.status === 'draft' && ['pending', 'collecting', 'ready'].includes(collectionFor(run)?.status || 'pending')))
const activeDeliveryRun = computed(() => runs.value.find(run => ['running', 'paused', 'stopping'].includes(run.status)))
const launchDisabled = computed(() => !browserReady.value || creating.value || activePipelineRun.value !== undefined || activeDeliveryRun.value !== undefined)
const launchButtonText = computed(() => {
  if (creating.value) return '正在启动自动流程…'
  if (activePipelineRun.value && !browserReady.value) return `任务 #${activePipelineRun.value.id} 等待扩展 v0.4.11`
  if (activePipelineRun.value) return collectionFor(activePipelineRun.value)?.status === 'ready'
    ? `任务 #${activePipelineRun.value.id} 等待确认企业`
    : `任务 #${activePipelineRun.value.id} 自动流程运行中`
  if (activeDeliveryRun.value) return `任务 #${activeDeliveryRun.value.id} 正在投递`
  return '启动自动流程'
})
const pipelineStep = computed(() => {
  if (!selected.value) return 0
  if (selected.value.status !== 'draft') return 4
  if (isNoMatches.value) return 2.5
  if (collectionStatus.value === 'ready') return 3
  if (isAnalyzing.value) return 2
  return 1
})
const automationPanelTitle = computed(() => {
  if (selected.value?.status !== 'draft') return '实时事件'
  if (isNoMatches.value) return '本地职位分析'
  if (collectionStatus.value === 'ready') return '确认待投企业'
  if (isAnalyzing.value) return '本地职位分析'
  return '扩展职位采集'
})
const collectionPhaseTitle = computed(() => isAnalyzing.value ? '本地服务正在分析职位' : 'Chrome 扩展正在采集职位')
const collectionProgressText = computed(() => {
  if (isAnalyzing.value) {
    const collected = collection.value?.collectedCount || 0
    const analyzed = collection.value?.analyzedCount || 0
    return collected ? `正在进行规则匹配并生成问候语（${analyzed} / ${collected}）` : '正在进行规则匹配并生成问候语。'
  }
  return collection.value?.currentKeyword ? `当前关键词：${collection.value.currentKeyword}` : '请保持已登录的 BOSS 页面和扩展连接，采集完成后会自动进入本地分析。'
})
const collectionElapsedSeconds = computed(() => {
  const startedAt = collection.value?.startedAt || selected.value?.updatedAt || selected.value?.createdAt
  const startedAtMs = startedAt ? Date.parse(startedAt) : Number.NaN
  return Number.isFinite(startedAtMs) ? Math.max(0, Math.floor((nowMs.value - startedAtMs) / 1_000)) : 0
})
const collectionElapsedText = computed(() => formatDuration(collectionElapsedSeconds.value))
const plannedCount = (run: AutomationRun) => Array.isArray(run.configSnapshot.plannedJobs) ? run.configSnapshot.plannedJobs.length : 0
const runStatusName = (run: AutomationRun) => {
  if (run.status !== 'draft') return statusName(run.status)
  const state = collectionFor(run)
  if (isNoMatchesState(state)) return '分析完成，暂无匹配'
  return ({ pending: '自动流程排队中', collecting: state?.phase === 'analyzing' ? '本地分析中' : '扩展采集中', ready: '待确认企业', no_matches: '分析完成，暂无匹配', failed: '自动流程失败' }[state?.status || 'pending'])
}
const collectionSummary = (run: AutomationRun) => {
  const state = collectionFor(run)
  if (isNoMatchesState(state)) return `采集 ${state?.collectedCount ?? 0} · 分析 ${state?.analyzedCount ?? state?.collectedCount ?? 0} · 通过 ${state?.approvedCount ?? 0} · 未通过 ${state?.rejectedCount ?? 0}`
  if (state?.status === 'collecting' && state.phase === 'analyzing') return `本地正在分析：${state.analyzedCount || 0} / ${state.collectedCount || 0}`
  if (state?.status === 'collecting') return state.currentKeyword ? `扩展正在采集：${state.currentKeyword}` : '扩展正在采集职位'
  if (state?.status === 'ready') return `自动准备完成，等待确认 ${plannedCount(run)} 个岗位`
  if (state?.status === 'failed') return state.message || state.reason || state.error || '自动流程失败，可重试'
  return '自动流程正在排队'
}
const collectionCount = (run: AutomationRun) => collectionFor(run)?.collectedCount ?? 0
const collectionExistingExcludedCount = (run: AutomationRun) => collectionFor(run)?.existingExcludedCount ?? 0
const collectionResultSummary = (run: AutomationRun) => {
  const state = collectionFor(run)
  const collected = state?.collectedCount ?? 0
  const analyzed = state?.analyzedCount ?? collected
  const approved = state?.approvedCount ?? plannedCount(run)
  const rejected = state?.rejectedCount ?? Math.max(0, analyzed - approved)
  const excluded = state?.existingExcludedCount ? ` · 本地去重 ${state.existingExcludedCount}` : ''
  return `采集 ${collected} · 分析 ${analyzed} · 通过 ${approved} · 未通过 ${rejected}${excluded}`
}
const pipelineStageClass = (stage: number) => ({ active: pipelineStep.value === stage, complete: pipelineStep.value > stage, pending: pipelineStep.value < stage })
const isErrorStatus = (status: string) => ['failed', 'blocked', 'cancelled'].includes(status)
const isRetryable = (run: AutomationRun) => ['failed', 'blocked', 'cancelled'].includes(run.status)
  && plannedCount(run) > run.successCount
const reviewOutcomeName = (outcome: AutomationReviewOutcome) => reviewOutcomeNames[outcome]
const reviewReasons = (job: AutomationReviewedJob) => job.reasons.length ? job.reasons : [{
  approved: '符合当前投递规则',
  rule_rejected: '未通过当前投递规则',
  duplicate: '已沟通过，跳过重复投递',
  material_error: '生成投递材料失败',
  analysis_error: '本地分析失败',
}[job.outcome]]
function extensionVersionAtLeast(version: string | undefined, minimum: [number, number, number]) {
  const values = (version?.match(/\d+/g) || []).slice(0, 3).map(Number)
  while (values.length < 3) values.push(0)
  for (let index = 0; index < minimum.length; index += 1) {
    if (values[index] !== minimum[index]) return values[index]! > minimum[index]!
  }
  return true
}
function formatDuration(totalSeconds: number) {
  if (totalSeconds < 60) return `${totalSeconds} 秒`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分钟`
}
function localizedCollectionError(error?: string) {
  if (!error) return '扩展未能完成职位采集，请确认扩展已连接并重新采集。'
  if (/timed out:\s*collect_jobs|collect_jobs.*timed out/i.test(error)) return '扩展读取职位超时。请确认 BOSS 搜索结果已正常显示，然后点击“重新采集”。'
  if (/timed out:\s*navigate_search|navigate_search.*timed out/i.test(error)) return '打开 BOSS 搜索页超时。请确认网络和登录状态后重新采集。'
  if (/browser extension (?:is not connected|disconnected)|Chrome 扩展未连接/i.test(error)) return 'Chrome 扩展连接已中断，请等待扩展恢复连接后重新采集。'
  if (/没有采集到完整职位|没有读取到完整职位|搜索结果页没有采集到完整职位/.test(error)) return '当前搜索页没有读取到完整职位，请确认搜索结果已加载后重新采集。'
  if (/^[\x00-\x7F\s:._-]+$/.test(error)) return '职位采集未完成，请检查 BOSS 页面和扩展连接后重新采集。'
  return error
}
const reasonText = (reason: string) => ({ 'plan-finished': '计划处理结束', 'user-requested': '用户已停止任务' }[reason] || reason)
const actionNames: Record<string, string> = { open_job: '打开岗位', open_chat: '打开沟通', validate_identity: '校验岗位身份', send_greeting: '发送问候语', send_resume: '发送简历' }
const eventText = (event: AutomationEvent) => {
  if (event.eventType === 'collection-queued') return event.payload.message || '系统已接管任务，将自动完成职位采集和本地分析'
  if (event.eventType === 'collection-started') return `Chrome 扩展开始采集，候选上限 ${event.payload.candidateLimit || event.payload.limit || '-'} 个职位，岗位间隔 ${Number(event.payload.collectionIntervalMs || 0) / 1000} 秒`
  if (event.eventType === 'collection-stage-changed') return event.payload.message || ({ queued: '自动流程已进入队列', searching: 'Chrome 扩展正在搜索职位', collecting: 'Chrome 扩展正在读取职位', analyzing: '本地服务正在分析职位', analysis_completed: '本地分析完成', awaiting_confirmation: '企业清单已生成，等待确认', failed: '自动流程执行失败' }[String(event.payload.phase)] || `阶段：${event.payload.phase || '-'}`)
  if (event.eventType === 'collection-keyword') return `正在采集关键词：${event.payload.keyword || event.payload.query || '-'}`
  if (event.eventType === 'collection-batch-finished') return `第 ${event.payload.batchNumber || '-'} 批完成：读取 ${event.payload.batchCount ?? '-'} 个，累计采集 ${event.payload.collectedCount ?? '-'} 个`
  if (event.eventType === 'analysis-started') return `开始分析 ${event.payload.collectedCount ?? '-'} 个采集职位`
  if (event.eventType === 'analysis-finished') return `采集 ${event.payload.collectedCount ?? '-'} 个职位，分析 ${event.payload.analyzedCount ?? '-'} 个，通过 ${event.payload.approvedCount ?? '-'}，未通过 ${event.payload.rejectedCount ?? '-'}`
  if (event.eventType === 'collection-finished') return `采集 ${event.payload.collectedCount ?? '-'} 个职位，生成 ${event.payload.approvedCount ?? event.payload.plannedCount ?? '-'} 个待确认岗位`
  if (event.eventType === 'collection-failed') return event.payload.message || event.payload.reason || event.payload.error || 'Chrome 扩展职位采集失败'
  if (event.payload.message || event.payload.reason) return event.payload.message || event.payload.reason
  if (event.eventType === 'status-changed') return `${statusName(event.payload.from)} → ${statusName(event.payload.to)}`
  if (event.eventType === 'run-created') return `目标 ${event.payload.target} 个岗位`
  if (event.eventType === 'retry-created') return event.payload.message || `重试任务 #${event.payload.sourceRunId || '-'} 的 ${event.payload.jobCount || '-'} 个岗位`
  if (event.eventType === 'plan-confirmed') return `已确认 ${event.payload.selectedCount} 个岗位：${(event.payload.companies || []).join('、')}`
  if (event.eventType === 'action-claimed') return `${actionNames[event.payload.actionType] || event.payload.actionType}已开始`
  if (event.eventType === 'action-finished') {
    const label = actionNames[event.payload.actionType] || event.payload.actionType
    return event.payload.status === 'succeeded' ? `${label}成功` : `${label}失败：${event.payload.error || '未通过安全校验'}`
  }
  return JSON.stringify(event.payload)
}

function applySelectedRun(run: AutomationRun) {
  const changedRun = selected.value?.id !== run.id
  const becameReady = !changedRun && collectionFor(selected.value)?.status !== 'ready' && collectionFor(run)?.status === 'ready'
  selected.value = run
  if (changedRun || becameReady) resetPlanSelection(run)
}

async function load() {
  const [runListResult, setupStatusResult, browserStatusResult] = await Promise.allSettled([
    api.automationRuns(),
    api.setupStatus(),
    api.browserStatus(),
  ])
  if (runListResult.status !== 'fulfilled') return
  const runList = runListResult.value
  runs.value = runList.items
  if (setupStatusResult.status === 'fulfilled') setup.value = setupStatusResult.value
  if (browserStatusResult.status === 'fulfilled') browser.value = browserStatusResult.value
  const current = selected.value ? runList.items.find(run => run.id === selected.value?.id) : runList.items[0]
  if (current) applySelectedRun(current)
  maybeRecoverAutomaticFlow(runList.items)
}

async function createRun() {
  if (launchDisabled.value) return
  const industry = collectionFilters.value.industry?.trim() || ''
  if (industry && !/^\d+(?:,\d+)*$/.test(industry)) {
    message.warning('公司行业编码只能填写数字；多个编码请使用英文逗号分隔')
    return
  }
  creating.value = true
  try {
    const normalizedCandidateLimit = Math.max(targetCount.value, Math.min(Number(candidateLimit.value) || 100, 500))
    const normalizedIntervalSeconds = Math.max(0, Math.min(Number(collectionIntervalSeconds.value) || 0, 30))
    const normalizedFilters = Object.fromEntries(
      Object.entries(collectionFilters.value).filter(([, value]) => value?.trim()),
    )
    const keywords = searchKeywordsInput.value.split(/[,，\n]/).map(value => value.trim()).filter(Boolean)
    candidateLimit.value = normalizedCandidateLimit
    collectionIntervalSeconds.value = normalizedIntervalSeconds
    const run = await api.createAutomationRun(targetCount.value, {
      candidateLimit: normalizedCandidateLimit,
      collectionIntervalMs: Math.round(normalizedIntervalSeconds * 1_000),
      collectionFilters: normalizedFilters,
      ...(keywords.length ? { searchKeywords: keywords } : {}),
      ...(collectionCityCode.value ? { cityCode: collectionCityCode.value } : {}),
    })
    await selectRun(run)
    message.success('自动流程已启动，将自动完成职位采集与本地分析')
    await load()
  } catch (error) {
    message.error((error as Error).message)
  } finally {
    creating.value = false
  }
}

async function collectRun(run: AutomationRun, silent = false) {
  if (collectingRunId.value !== undefined) return
  collectingRunId.value = run.id
  applySelectedRun(run)
  try {
    const collected = await api.collectAutomationRun(run.id)
    applySelectedRun(collected)
    await load()
    await loadEvents(run.id)
    const completedCollection = collectionFor(selected.value)
    if (!silent && completedCollection?.status === 'ready') {
      const count = plannedCount(selected.value || collected)
      count ? message.success(`自动准备完成，请确认 ${count} 个待投岗位`) : message.warning('自动流程完成，但没有岗位通过本地匹配规则')
    } else if (!silent && isNoMatchesState(completedCollection)) {
      message.info('采集与分析完成，暂无符合规则的岗位')
    } else if (!silent) {
      message.info('自动流程已恢复，将继续采集和分析')
    }
  } catch (error) {
    await Promise.allSettled([load(), loadEvents(run.id)])
    if (!silent) {
      isNoMatchesState(collectionFor(selected.value))
        ? message.info('采集与分析完成，暂无符合规则的岗位')
        : message.error((error as Error).message)
    }
  } finally {
    collectingRunId.value = undefined
  }
}

function maybeRecoverAutomaticFlow(runList: AutomationRun[]) {
  const recoverableIds = new Set(runList
    .filter(run => run.status === 'draft' && ['pending', 'collecting'].includes(collectionFor(run)?.status || 'pending'))
    .map(run => run.id))
  for (const runId of recoveryStates.keys()) {
    if (!recoverableIds.has(runId)) recoveryStates.delete(runId)
  }
  if (!browserReady.value || collectingRunId.value !== undefined) return
  const candidate = runList.find(run => run.status === 'draft' && ['pending', 'collecting'].includes(collectionFor(run)?.status || 'pending'))
  if (!candidate) return
  const state = collectionFor(candidate)
  const observedUpdatedAt = state?.updatedAt || candidate.updatedAt || candidate.createdAt
  const previous = recoveryStates.get(candidate.id)
  const recovery = previous?.observedUpdatedAt === observedUpdatedAt
    ? previous
    : { attempts: 0, nextAttemptAt: 0, observedUpdatedAt }
  recoveryStates.set(candidate.id, recovery)
  const age = runUpdatedAge(candidate)
  const minimumAge = state?.status === 'collecting' ? COLLECTION_STALE_AFTER_MS : 2_000
  if (!Number.isFinite(age) || age < minimumAge) return
  if (recovery.attempts >= COLLECTION_RECOVERY_MAX_ATTEMPTS || Date.now() < recovery.nextAttemptAt) return
  recovery.attempts += 1
  recovery.nextAttemptAt = Date.now() + COLLECTION_RECOVERY_BASE_DELAY_MS * (2 ** (recovery.attempts - 1))
  void collectRun(candidate, true)
}

async function collectSelectedRun() {
  if (!selected.value) return
  recoveryStates.delete(selected.value.id)
  await collectRun(selected.value)
}
async function control(run: AutomationRun, action: 'start' | 'pause' | 'resume' | 'stop') { try { selected.value = await api.controlAutomationRun(run.id, action); await load(); await loadEvents(run.id) } catch (error) { message.error((error as Error).message) } }
function retryRun(run: AutomationRun) {
  Modal.confirm({
    title: `确认重试任务 #${run.id}？`,
    content: '系统只会创建一个新任务来处理失败或未完成岗位；已成功岗位不会重复执行。若上次发送结果为“不确定”，仍可能存在重复问候风险，请确认 BOSS 聊天记录后再继续。',
    okText: '确认重试',
    cancelText: '取消',
    async onOk() {
      retryingRunId.value = run.id
      try {
        const retried = await api.retryAutomationRun(run.id)
        await selectRun(retried)
        await load()
        message.success(`已创建重试任务 #${retried.id}`)
      } catch (error) {
        message.error((error as Error).message)
        throw error
      } finally {
        retryingRunId.value = undefined
      }
    },
  })
}
function resetPlanSelection(run: AutomationRun) { selectionRunId.value = run.id; selectedJobIds.value = (Array.isArray(run.configSnapshot.plannedJobs) ? run.configSnapshot.plannedJobs : []).map((job: PlannedAutomationJob) => job.jobId) }
function toggleJob(jobId: string) { selectedJobIds.value = selectedJobIds.value.includes(jobId) ? selectedJobIds.value.filter(id => id !== jobId) : [...selectedJobIds.value, jobId] }
function toggleAllJobs() { selectedJobIds.value = allJobsSelected.value ? [] : plannedJobs.value.map(job => job.jobId) }
async function confirmAndStart() {
  if (!selected.value || collectionStatus.value !== 'ready') return message.warning('请先等待 Chrome 扩展完成职位采集')
  if (!selectedJobIds.value.length) return message.warning('请至少选择一个待投岗位')
  starting.value = true
  try {
    const runId = selected.value.id
    selected.value = await api.controlAutomationRun(runId, 'start', selectedJobIds.value)
    message.success(`已确认 ${selectedJobIds.value.length} 个岗位，执行器即将开始处理`)
    await load()
    await loadEvents(runId)
  } catch (error) { message.error((error as Error).message) } finally { starting.value = false }
}
async function loadEvents(id: number) {
  report.value = await api.automationReport(id)
  events.value = report.value.events
  applySelectedRun(report.value.run)
}
async function selectRun(run: AutomationRun) {
  applySelectedRun(run)
  await loadEvents(run.id)
  stream?.close()
  stream = new EventSource(`/v1/automation/runs/${run.id}/events/stream?after=${events.value.at(-1)?.sequence || 0}`)
  stream.onmessage = () => void loadEvents(run.id)
}

onMounted(() => {
  refreshTimer = setInterval(() => { void load(); if (selected.value) void loadEvents(selected.value.id) }, 3000)
  elapsedTimer = setInterval(() => { nowMs.value = Date.now() }, 1000)
})
onBeforeUnmount(() => {
  stream?.close()
  if (refreshTimer) clearInterval(refreshTimer)
  if (elapsedTimer) clearInterval(elapsedTimer)
})
useRefresh(load)
</script>

<style scoped>
.automation-collection-settings {
  margin-top: 12px;
  padding: 16px 18px;
}

.automation-collection-settings header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.automation-collection-settings header > div {
  display: grid;
  gap: 3px;
}

.automation-collection-settings header strong {
  font-size: 12px;
}

.automation-collection-settings header span,
.automation-collection-settings > p {
  color: var(--muted);
  font-size: 11px;
}

.automation-collection-settings header > span {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f3e4d2;
  color: #75471d;
  font-weight: 700;
}

.automation-filter-grid {
  margin-top: 13px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.automation-filter-grid label {
  min-width: 0;
  display: grid;
  gap: 5px;
  color: var(--muted);
  font-size: 11px;
}

.automation-filter-grid label.wide {
  grid-column: span 2;
}

.automation-filter-grid input,
.automation-filter-grid select {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  outline: 0;
  background: #fff;
  color: var(--ink);
}

.automation-filter-grid input:focus,
.automation-filter-grid select:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgb(23 107 85 / 10%);
}

.automation-collection-settings > p {
  margin: 10px 0 0;
  line-height: 1.6;
}

.automation-pipeline {
  margin-top: 12px;
  padding: 14px 18px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.automation-retry-action :deep(.ant-btn-primary) {
  border-color: #176b55;
  background: #176b55;
  color: #fff;
  font-weight: 700;
  box-shadow: 0 2px 0 rgb(10 74 57 / 18%);
}

.automation-retry-action :deep(.ant-btn-primary:not(:disabled):hover),
.automation-retry-action :deep(.ant-btn-primary:not(:disabled):focus-visible) {
  border-color: #0f5745;
  background: #0f5745;
  color: #fff;
}

.automation-retry-action :deep(.ant-btn-primary:disabled),
.automation-retry-action :deep(.ant-btn-primary.ant-btn-loading) {
  border-color: #75aa9b;
  background: #75aa9b;
  color: #fff;
  opacity: 1;
  box-shadow: none;
}

.automation-pipeline-stage {
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--surface-soft);
  transition: border-color .18s, background .18s, box-shadow .18s;
}

.automation-pipeline-stage.active {
  border-color: #89c6b1;
  background: var(--brand-soft);
  box-shadow: 0 0 0 2px rgb(40 126 99 / 8%);
}

.automation-pipeline-stage.complete {
  border-color: #b9ddcf;
  background: #f5fbf8;
}

.automation-pipeline-stage.pending {
  opacity: .62;
}

.automation-pipeline-index {
  width: 25px;
  height: 25px;
  flex: 0 0 25px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #dce6e1;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}

.automation-pipeline-stage.active .automation-pipeline-index,
.automation-pipeline-stage.complete .automation-pipeline-index {
  background: var(--brand);
  color: #fff;
}

.automation-pipeline-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.automation-pipeline-copy strong {
  font-size: 12px;
  white-space: nowrap;
}

.automation-pipeline-copy small {
  overflow: hidden;
  color: var(--muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.automation-pipeline-arrow {
  color: #98aaa2;
  font-size: 15px;
}

.automation-activity {
  width: min(520px, 100%);
  margin: 14px auto 10px;
  padding: 10px 12px;
  border-radius: 9px;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 11px;
  font-weight: 700;
}

.automation-activity i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--brand);
  box-shadow: 0 0 0 0 rgb(40 126 99 / 35%);
  animation: automation-pulse 1.6s ease-out infinite;
}

@keyframes automation-pulse {
  70% { box-shadow: 0 0 0 7px rgb(40 126 99 / 0%); }
  100% { box-shadow: 0 0 0 0 rgb(40 126 99 / 0%); }
}

.automation-progress-metrics {
  display: flex;
  justify-content: center;
  gap: 18px;
  color: var(--muted);
  font-size: 11px;
}

.automation-no-matches {
  padding: 17px;
  border: 1px solid #b9dbcf;
  border-radius: 12px;
  background: #f6fbf8;
}

.automation-no-matches-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.automation-no-matches-heading > div {
  min-width: 0;
}

.automation-no-matches-heading strong {
  color: var(--ink);
  font-size: 13px;
}

.automation-no-matches-heading p {
  max-width: 660px;
  margin: 7px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.65;
}

.automation-result-metrics {
  margin-top: 15px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 8px;
}

.automation-result-metrics > div {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 9px;
  display: grid;
  gap: 4px;
  background: #fff;
}

.automation-result-metrics strong {
  color: var(--brand-deep);
  font-size: 17px;
}

.automation-result-metrics span {
  color: var(--muted);
  font-size: 11px;
}

.automation-review-results {
  margin-top: 15px;
  display: grid;
  gap: 8px;
}

.automation-review-heading {
  padding: 0 2px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--ink);
  font-size: 12px;
}

.automation-review-heading span {
  color: var(--muted);
  font-weight: 400;
}

.automation-reviewed-job {
  padding: 12px 13px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}

.automation-reviewed-job header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.automation-reviewed-job header > div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.automation-reviewed-job header strong {
  overflow-wrap: anywhere;
  font-size: 11px;
}

.automation-reviewed-job header span {
  color: var(--muted);
  font-size: 11px;
}

.automation-reviewed-job header em {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: #f6ece2;
  color: #946221;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
  white-space: nowrap;
}

.automation-reviewed-job header em.outcome-approved {
  background: var(--brand-soft);
  color: var(--brand-deep);
}

.automation-reviewed-job header em.outcome-duplicate {
  background: #eef2ef;
  color: var(--muted);
}

.automation-reviewed-job header em.outcome-material_error,
.automation-reviewed-job header em.outcome-analysis_error {
  background: #f8e7e7;
  color: var(--danger);
}

.automation-reviewed-meta {
  margin: 8px 0 0;
  display: flex;
  flex-wrap: wrap;
  gap: 5px 12px;
  color: var(--muted);
  font-size: 11px;
}

.automation-reviewed-job ul {
  margin: 9px 0 0;
  padding: 9px 10px 9px 26px;
  border-radius: 8px;
  background: var(--surface-soft);
}

.automation-reviewed-job li {
  display: list-item;
  margin: 3px 0;
  padding: 0;
  border: 0;
  color: #52645b;
  font-size: 11px;
  line-height: 1.55;
}

.automation-review-unavailable {
  margin: 14px 0 0;
  padding: 11px 12px;
  border-radius: 8px;
  background: #fff;
  color: var(--muted);
  font-size: 11px;
}

.automation-collection-history {
  margin: 14px 16px;
  padding: 14px;
  border: 1px solid #b9dbcf;
  border-radius: 11px;
  background: #f6fbf8;
}

.automation-collection-history-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.automation-collection-history-heading > div {
  min-width: 0;
}

.automation-collection-history-heading strong {
  color: var(--ink);
  font-size: 12px;
}

.automation-collection-history-heading p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 11px;
}

.automation-collection-history-heading > span {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand-deep);
  font-size: 10px;
  font-weight: 700;
}

.automation-review-details {
  margin-top: 13px;
}

.automation-review-details summary {
  width: fit-content;
  cursor: pointer;
  color: var(--brand-deep);
  font-size: 12px;
  font-weight: 700;
}

.automation-review-details[open] summary {
  margin-bottom: 4px;
}

@media (max-width: 1000px) {
  .automation-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .automation-pipeline {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .automation-pipeline-arrow {
    display: none;
  }

  .automation-pipeline-stage {
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .automation-collection-settings header {
    align-items: stretch;
    flex-direction: column;
  }

  .automation-collection-settings header > span {
    align-self: flex-start;
  }

  .automation-filter-grid {
    grid-template-columns: 1fr;
  }

  .automation-filter-grid label.wide {
    grid-column: auto;
  }

  .automation-pipeline {
    grid-template-columns: 1fr;
  }

  .automation-pipeline-copy small {
    white-space: normal;
  }

  .automation-no-matches-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .automation-collection-history-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .automation-collection-history-heading > span {
    align-self: flex-start;
  }

  .automation-result-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
