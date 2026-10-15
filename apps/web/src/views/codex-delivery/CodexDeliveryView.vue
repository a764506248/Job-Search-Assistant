<template>
  <div class="view active-view codex-delivery-view">
    <section class="notice-card automation-command panel">
      <div>
        <p class="eyebrow">ISOLATED IPHONE WORKFLOW</p>
        <h2>Codex 单岗投递</h2>
        <p>这是独立的手机投递链路，只读取你的档案、项目、简历和规则，不会创建或修改旧的网页自动投递任务。</p>
      </div>
      <span class="isolation-badge">手机端独立流程</span>
    </section>

    <section class="panel runs-panel" aria-labelledby="codex-progress-title">
      <div class="panel-heading progress-title">
        <div>
          <p class="eyebrow">LIVE PROGRESS</p>
          <h3 id="codex-progress-title">Codex 投递进度</h3>
          <p class="progress-subtitle">仅显示最近 20 次任务；点击任务查看统计与岗位明细。</p>
        </div>
        <a-button :loading="loading" @click="loadAll">刷新进度</a-button>
      </div>
      <div v-if="runs.length" class="run-list">
        <article v-for="(run, index) in runs" :key="run.id" class="run-card" :class="{ 'run-card-current': index === 0, 'run-card-open': expandedRunId === run.id }">
          <button type="button" class="run-summary" :aria-expanded="expandedRunId === run.id" @click="toggleRun(run.id)">
            <span class="run-identity"><strong>#{{ run.id }} · {{ run.configSnapshot?.name || '手机投递' }}</strong><small>{{ formatRunTime(run.createdAt) }}</small></span>
            <span class="run-count">投递 <strong>{{ run.deliveredCount }}/{{ run.targetDeliveryCount }}</strong></span>
            <span class="run-count">扫描 {{ run.scannedCount }} · 分析 {{ run.analyzedCount }}</span>
            <span class="run-status" :class="`run-status-${run.status}`">{{ statusText(run.status) }}</span>
            <span class="run-chevron" aria-hidden="true">{{ expandedRunId === run.id ? '⌃' : '⌄' }}</span>
          </button>
          <div v-if="expandedRunId === run.id" class="run-expanded">
            <div class="run-progress-heading"><span>成功投递</span><strong>{{ run.deliveredCount }} <small>/ {{ run.targetDeliveryCount }}</small></strong></div>
            <div class="progress-track" role="progressbar" :aria-valuenow="progress(run)" aria-valuemin="0" aria-valuemax="100" :aria-label="`任务 ${run.id} 投递进度`"><span :style="{ width: progress(run) + '%' }"></span></div>
            <div class="metrics">
              <span><strong>{{ run.scannedCount }}</strong><small>已扫描</small></span>
              <span><strong>{{ run.capturedCount }}</strong><small>已采集</small></span>
              <span><strong>{{ run.analyzedCount }}</strong><small>已分析</small></span>
              <span><strong>{{ run.eligibleCount }}</strong><small>符合要求</small></span>
              <span><strong>{{ run.skippedCount }}</strong><small>已跳过</small></span>
              <span><strong>{{ run.failedCount }}</strong><small>失败</small></span>
              <span><strong>{{ run.uncertainCount }}</strong><small>待确认</small></span>
            </div>
            <div class="run-footer">
              <small>{{ run.currentSourceTab || '尚未进入列表' }} · {{ run.currentStage }}<template v-if="run.stopReason"> · {{ run.stopReason }}</template></small>
              <a-button size="small" @click="loadRunDetail(run.id)">查看岗位明细</a-button>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="progress-empty">
        <div class="progress-empty-icon" aria-hidden="true"><span>01</span><span>02</span><span>03</span></div>
        <div>
          <strong>还没有投递任务</strong>
          <p>完成下方配置并交给 Codex 启动后，扫描、分析与投递进度会实时显示在这里。</p>
        </div>
      </div>
      <div v-if="selectedRun" class="step-panel">
        <div class="section-title"><h4>任务 #{{ selectedRun.id }} 岗位明细</h4><a-button size="small" @click="selectedRun = null">关闭</a-button></div>
        <article v-for="step in selectedRun.steps || []" :key="step.id" class="step-card">
          <div class="run-head"><strong>{{ step.snapshot?.title || step.platformJobId }}</strong><span>{{ step.status }}</span></div>
          <p>{{ step.snapshot?.companyName || '公司待补充' }} · {{ step.sourceTab || '未知来源' }} · 资料相似度 {{ step.score ?? '—' }} 分</p>
          <p>当前动作：{{ step.currentAction }}<template v-if="step.listPosition !== null"> · 列表第 {{ step.listPosition }} 个</template></p>
          <p v-if="step.decisionReasons.length">{{ step.decisionReasons.join('；') }}</p>
          <blockquote v-if="step.greeting">{{ step.greeting }}</blockquote>
          <blockquote v-if="step.evidence?.sentText" class="sent-text"><strong>手机实际发送：</strong>{{ step.evidence.sentText }}</blockquote>
          <small v-if="step.evidence?.inputMethod">输入方式：{{ step.evidence.inputMethod }}<template v-if="step.evidence?.resumeOutcome"> · 简历结果：{{ step.evidence.resumeOutcome }}</template></small>
          <small v-if="step.errorMessage" class="step-error">{{ step.errorMessage }}</small>
        </article>
        <p v-if="!selectedRun.steps?.length" class="empty-copy">这次任务还没有岗位快照。</p>
      </div>
    </section>

    <section class="panel connection-panel">
      <div class="panel-heading">
        <div><p class="eyebrow">CONNECTION</p><h3>Codex 连接</h3></div>
        <a-button type="primary" :loading="creatingKey" @click="createKey">生成 Agent Key</a-button>
      </div>
      <div class="connection-grid">
        <label>服务地址<input :value="serviceUrl" readonly /></label>
        <div class="connection-help">
          <strong>Codex 需要两项信息</strong>
          <span>Base URL：{{ serviceUrl }}</span>
          <span>Agent Key：仅在生成后显示一次，不包含 BOSS 密码。</span>
        </div>
      </div>
      <div v-if="newPlaintextKey" class="secret-box" role="status">
        <div><strong>请立即复制并安全保存</strong><span>关闭或刷新后无法再次查看完整 Key。</span></div>
        <code>{{ newPlaintextKey }}</code>
        <a-button @click="copyKey">复制 Key</a-button>
      </div>
      <div class="key-list">
        <div v-for="key in keys" :key="key.id" class="key-row">
          <div><strong>{{ key.name }}</strong><span>jsa_agent_{{ key.keyPrefix }}_•••• · {{ key.scopes.join('、') }}</span><small>创建：{{ formatRunTime(key.createdAt) }} · 最近使用：{{ key.lastUsedAt ? formatRunTime(key.lastUsedAt) : '尚未使用' }} · 到期：{{ key.expiresAt ? formatRunTime(key.expiresAt) : '长期有效' }}</small></div>
          <span :class="key.revokedAt ? 'status-muted' : 'status-ready'">{{ key.revokedAt ? '已撤销' : '可用' }}</span>
          <a-button v-if="!key.revokedAt" danger @click="revokeKey(key.id)">撤销</a-button>
        </div>
        <p v-if="!keys.length" class="empty-copy">还没有 Agent Key。</p>
      </div>
    </section>

    <form class="panel config-panel" @submit.prevent="saveConfig">
      <div class="panel-heading">
        <div><p class="eyebrow">MOBILE FILTERS</p><h3>手机筛选与投递计划</h3></div>
        <a-button type="primary" html-type="submit" :loading="saving">保存配置</a-button>
      </div>
      <div class="config-toolbar">
        <label>选择投递方案
          <select :value="config.id ?? ''" @change="selectConfig(($event.target as HTMLSelectElement).value)">
            <option value="">新方案（未保存）</option>
            <option v-for="item in configs" :key="item.id" :value="item.id">{{ item.name }}{{ item.isDefault ? ' · 默认' : '' }}</option>
          </select>
        </label>
        <a-button @click="newConfig">新建方案</a-button>
        <span>保存后可通过 Agent Key 选择方案；历史任务保留创建时的配置快照。</span>
      </div>

      <div class="field-grid">
        <label class="wide">配置名称<input v-model.trim="config.name" required /></label>
        <label class="choice wide"><input v-model="config.isDefault" type="checkbox" />设为默认投递方案</label>
        <fieldset class="wide">
          <legend>来源页签（按勾选顺序由 Codex 处理）</legend>
          <label v-for="tab in sourceTabOptions" :key="tab" class="choice">
            <input v-model="config.sourceTabs" type="checkbox" :value="tab" />{{ tab }}
          </label>
        </fieldset>
        <label>城市名称<input v-model.trim="config.cityName" placeholder="例如：深圳" /></label>
        <label>城市编码<input v-model.trim="config.cityCode" placeholder="例如：101280600" /></label>
        <label class="wide">关键词<input v-model="keywordText" placeholder="多个关键词用逗号分隔" /></label>
        <label>求职意向<input v-model="intentionText" placeholder="多个意向用逗号分隔" /></label>
        <label>推荐标签<input v-model="recommendedTagText" placeholder="例如：Go、分布式技术、视觉算法" /></label>
      </div>

      <div class="filter-groups">
        <fieldset v-for="group in multipleGroups" :key="group.key">
          <legend>{{ group.label }}</legend>
          <label v-for="item in group.options" :key="item.label" class="choice">
            <input
              type="checkbox"
              :checked="hasOption(group.key, item.label)"
              @change="toggleOption(group.key, item)"
            />{{ item.label }}
          </label>
        </fieldset>
      </div>

      <div class="field-grid plan-grid">
        <label>BOSS 活跃
          <select v-model="bossActivityLabel">
            <option v-for="item in bossActivityOptions" :key="item.label" :value="item.label">{{ item.label }}</option>
          </select>
        </label>
        <label>薪资范围
          <select v-model="salaryLabel">
            <option v-for="item in salaryOptions" :key="item.label" :value="item.label">{{ item.label }}</option>
          </select>
        </label>
        <template v-if="salaryLabel === '自定义薪资'">
          <label>最低月薪（K）<input v-model.number="config.salaryMinK" type="number" min="0" max="1000" required /></label>
          <label>最高月薪（K）<input v-model.number="config.salaryMaxK" type="number" min="0" max="1000" required /></label>
        </template>
        <label>目标成功投递数<input v-model.number="config.targetDeliveryCount" type="number" min="1" max="100" required /></label>
        <label>最大扫描职位数<input v-model.number="config.maxScanCount" type="number" min="1" max="1000" required /></label>
        <label>岗位处理间隔（秒）<input v-model.number="config.intervalSeconds" type="number" min="1" max="60" step="0.5" /></label>
        <label>最低资料相似度<input v-model.number="config.minimumScore" type="number" min="0" max="100" /></label>
        <label>最低问候语置信度<input v-model.number="config.minimumCustomizationConfidence" type="number" min="0" max="100" /></label>
        <label>确认模式
          <select v-model="config.confirmationMode"><option value="automatic">符合后自动投递</option><option value="per_job">每岗确认</option></select>
        </label>
        <label>问候语策略
          <select v-model="config.greetingStrategy"><option value="custom">模型按岗位定制</option><option value="default">使用兜底问候语</option></select>
        </label>
        <label>使用简历
          <select v-model="config.resumeId"><option :value="null">暂不指定</option><option v-for="resume in resumes" :key="resume.id" :value="resume.id">{{ resume.name }}</option></select>
        </label>
        <label class="wide">兜底问候语<textarea v-model="config.fallbackGreeting" rows="3" maxlength="2000"></textarea></label>
        <label class="choice wide"><input v-model="config.stopOnUncertain" type="checkbox" />结果不确定时立即停止，不自动重发</label>
        <label class="choice wide"><input v-model="config.sendResume" type="checkbox" />沟通成功后发送所选简历（由 Codex 执行前再次确认）</label>
      </div>
    </form>

  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useRefresh } from '../../composables/useRefresh'
import { api } from '../../services/api'
import type { LibraryRecord } from '../../types'
import type { AgentKeyRecord, CodexDeliveryConfig, CodexDeliveryRun, PlatformOption } from '../../types/codex-delivery'

type MultiKey = 'experience' | 'degree' | 'companyScale' | 'benefits' | 'financing' | 'industries'

const sourceTabOptions: Array<'推荐' | '附近' | '最新'> = ['推荐', '附近', '最新']
const experienceOptions = options(['全部', '1年以内', '1-3年', '3-5年', '5-10年', '10年以上', '应届生', '在校生'])
const degreeOptions = options(['全部', '中专/中技', '高中', '大专', '本科', '硕士', '博士', '初中及以下'])
const scaleOptions = options(['全部', '0-20人', '20-99人', '100-499人', '500-999人', '1000-9999人', '10000人以上'])
const benefitOptions = options(['周末双休', '五险', '五险一金', '8小时工作制', '带薪年假', '餐补', '弹性工作制'])
const financingOptions = options(['全部', '未融资', '天使轮', 'A轮', 'B轮', 'C轮', '不需要融资', '已上市'])
const industryOptions = options(['医疗健康', '互联网', '电子/半导体/集成电路', '计算机软件'])
const bossActivityOptions = options(['全部', '今日活跃', '3日内活跃', '本周活跃', '本月活跃'])
const salaryOptions = options(['全部', '15K以下', '15-25K', '25-35K', '35-45K', '45K以上', '自定义薪资'])
const multipleGroups: Array<{ key: MultiKey; label: string; options: PlatformOption[] }> = [
  { key: 'experience', label: '工作经验', options: experienceOptions },
  { key: 'degree', label: '学历', options: degreeOptions },
  { key: 'companyScale', label: '公司规模', options: scaleOptions },
  { key: 'benefits', label: '福利待遇', options: benefitOptions },
  { key: 'financing', label: '融资阶段', options: financingOptions },
  { key: 'industries', label: '行业', options: industryOptions },
]

const keys = ref<AgentKeyRecord[]>([])
const configs = ref<CodexDeliveryConfig[]>([])
const runs = ref<CodexDeliveryRun[]>([])
const expandedRunId = ref<number | null>(null)
const selectedRun = ref<CodexDeliveryRun | null>(null)
const resumes = ref<LibraryRecord[]>([])
const newPlaintextKey = ref('')
const creatingKey = ref(false)
const saving = ref(false)
const loading = ref(false)
const keywordText = ref('')
const intentionText = ref('')
const recommendedTagText = ref('')
const bossActivityLabel = ref('全部')
const salaryLabel = ref('全部')
const config = reactive<CodexDeliveryConfig>(defaultConfig())
const configuredAgentBaseUrl = String(import.meta.env.VITE_AGENT_BASE_URL || '').trim()
const serviceUrl = computed(() => configuredAgentBaseUrl || (import.meta.env.DEV
  ? `${window.location.protocol}//${window.location.hostname}:8765`
  : window.location.origin))

function options(labels: string[]): PlatformOption[] { return labels.map(label => ({ label })) }
function defaultConfig(): CodexDeliveryConfig {
  return {
    name: '默认手机投递', isDefault: true, enabled: true, sourceTabs: ['推荐', '附近', '最新'],
    jobIntentions: [], keywords: [], cityCode: null, cityName: null, experience: [], degree: [], companyScale: [],
    bossActivity: { label: '全部' }, salaryMode: 'all', salaryCode: null, salaryMinK: null, salaryMaxK: null,
    benefits: [], financing: [], industries: [], recommendedTags: [], targetDeliveryCount: 1, maxScanCount: 20,
    intervalSeconds: 2, minimumScore: 60, minimumCustomizationConfidence: 50, resumeId: null, sendResume: false,
    greetingStrategy: 'custom', fallbackGreeting: '您好，我对贵司的这个岗位很感兴趣，希望有机会进一步沟通，谢谢。',
    confirmationMode: 'automatic', stopOnUncertain: true,
  }
}

function hasOption(key: MultiKey, label: string) { return config[key].some(item => item.label === label) }
function toggleOption(key: MultiKey, item: PlatformOption) {
  const values = config[key]
  const index = values.findIndex(value => value.label === item.label)
  if (index >= 0) values.splice(index, 1)
  else values.push({ ...item })
}

async function loadAll() {
  loading.value = true
  try {
    const [keyResult, configResult, runResult, resumeResult] = await Promise.all([
      api.agentKeys(), api.codexDeliveryConfigs(), api.codexDeliveryRuns(), api.library('resumes'),
    ])
    keys.value = keyResult.items
    configs.value = configResult.items
    runs.value = runResult.items
    resumes.value = resumeResult.items
    if (expandedRunId.value !== null && !runs.value.some(run => run.id === expandedRunId.value)) expandedRunId.value = null
    if (configResult.items.length) {
      loadConfig(configResult.items.find(item => item.id === config.id) || configResult.items[0])
    }
  } catch (error) { message.error((error as Error).message) }
  finally { loading.value = false }
}

function loadConfig(value: CodexDeliveryConfig) {
  Object.assign(config, defaultConfig(), value)
  keywordText.value = config.keywords.join('，')
  intentionText.value = config.jobIntentions.map(item => item.label).join('，')
  recommendedTagText.value = config.recommendedTags.map(item => item.label).join('，')
  bossActivityLabel.value = config.bossActivity?.label || '全部'
  salaryLabel.value = config.salaryMode === 'custom' ? '自定义薪资' : config.salaryCode || '全部'
}

function newConfig() {
  loadConfig({ ...defaultConfig(), name: `新投递方案 ${configs.value.length + 1}`, isDefault: !configs.value.length })
  delete config.id
}

function selectConfig(value: string) {
  if (!value) { newConfig(); return }
  const selected = configs.value.find(item => item.id === Number(value))
  if (selected) loadConfig(selected)
}

function toggleRun(id: number) {
  expandedRunId.value = expandedRunId.value === id ? null : id
  if (selectedRun.value?.id !== expandedRunId.value) selectedRun.value = null
}

function formatRunTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function saveConfig() {
  if (!config.sourceTabs.length) { message.warning('请至少选择一个来源页签'); return }
  if (config.maxScanCount < config.targetDeliveryCount) { message.warning('最大扫描数不能小于目标投递数'); return }
  saving.value = true
  try {
    config.keywords = keywordText.value.split(/[,，\n]/).map(value => value.trim()).filter(Boolean)
    config.jobIntentions = splitOptions(intentionText.value)
    config.recommendedTags = splitOptions(recommendedTagText.value)
    config.bossActivity = { label: bossActivityLabel.value }
    config.salaryMode = salaryLabel.value === '全部' ? 'all' : salaryLabel.value === '自定义薪资' ? 'custom' : 'preset'
    config.salaryCode = ['全部', '自定义薪资'].includes(salaryLabel.value) ? null : salaryLabel.value
    if (config.salaryMode !== 'custom') { config.salaryMinK = null; config.salaryMaxK = null }
    const saved = await api.saveCodexDeliveryConfig({ ...config })
    loadConfig(saved)
    configs.value = await api.codexDeliveryConfigs().then(result => result.items)
    message.success('Codex 投递配置已保存')
  } catch (error) { message.error((error as Error).message) }
  finally { saving.value = false }
}

async function createKey() {
  creatingKey.value = true
  try {
    const result = await api.createAgentKey('本机 Codex')
    newPlaintextKey.value = result.plaintext
    keys.value.unshift(result.key)
    message.success('Agent Key 已生成，仅显示这一次')
  } catch (error) { message.error((error as Error).message) }
  finally { creatingKey.value = false }
}

async function loadRunDetail(id: number) {
  try { selectedRun.value = await api.codexDeliveryRun(id) }
  catch (error) { message.error((error as Error).message) }
}

async function copyKey() {
  await navigator.clipboard.writeText(newPlaintextKey.value)
  message.success('Agent Key 已复制')
}

function revokeKey(id: number) {
  Modal.confirm({
    title: '撤销这个 Agent Key？', content: '使用该 Key 的 Codex 将立即无法继续请求。', okText: '撤销', okType: 'danger', cancelText: '取消',
    async onOk() {
      try {
        const result = await api.revokeAgentKey(id)
        keys.value = keys.value.map(item => item.id === id ? result.key : item)
        message.success('Agent Key 已撤销')
      } catch (error) { message.error((error as Error).message) }
    },
  })
}

function progress(run: CodexDeliveryRun) { return Math.min(100, Math.round(run.deliveredCount / run.targetDeliveryCount * 100)) }
function statusText(status: string) { return ({ running: '执行中', completed: '已完成', paused: '已暂停', stopped: '已停止', failed: '失败', uncertain: '待人工确认' } as Record<string, string>)[status] || status }
function splitOptions(value: string): PlatformOption[] { return value.split(/[,，\n]/).map(label => label.trim()).filter(Boolean).map(label => ({ label })) }

useRefresh(loadAll)
</script>

<style scoped>
.codex-delivery-view { display: grid; gap: 18px; }
.codex-delivery-view .panel { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); overflow: hidden; }
.notice-card { display: flex; align-items: center; justify-content: space-between; }
.notice-card h2, .section-title h3 { margin: 2px 0 8px; }
.notice-card p:last-child { margin: 0; color: #617069; }
.isolation-badge { border-radius: 999px; padding: 8px 14px; background: var(--brand-soft); color: var(--brand-deep); font-size: 12px; font-weight: 700; white-space: nowrap; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.section-title p, .section-title h3 { margin-top: 0; }
.codex-delivery-view .panel-heading { padding: 18px 22px; margin: 0; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); }
.codex-delivery-view .panel-heading h3 { margin: 0; font-size: 18px; }
.codex-delivery-view .panel-heading .eyebrow { margin-bottom: 5px; }
.progress-title { align-items: center; }
.progress-subtitle { margin: 0; color: #6c7e74; font-size: 13px; font-weight: 400; }
.progress-empty { display: flex; align-items: center; gap: 22px; min-height: 126px; margin: 18px 22px; padding: 18px 22px; border: 1px dashed #b9d9ca; border-radius: 12px; background: var(--surface-soft); }
.progress-empty > div:last-child { min-width: 0; }
.progress-empty strong { display: block; margin-bottom: 5px; color: #173f32; font-size: 17px; }
.progress-empty p { max-width: 620px; margin: 0; color: #698076; line-height: 1.65; }
.progress-empty-icon { display: flex; flex: 0 0 auto; align-items: center; padding-left: 10px; }
.progress-empty-icon span { display: grid; place-items: center; width: 42px; height: 42px; margin-left: -10px; border: 2px solid #f5faf7; border-radius: 50%; background: #d7eee2; color: #236a52; font-size: 11px; font-weight: 800; }
.progress-empty-icon span:nth-child(2) { background: #bce1d0; }.progress-empty-icon span:nth-child(3) { background: #237757; color: #fff; }
.config-toolbar { display: flex; align-items: end; flex-wrap: wrap; gap: 10px 14px; padding: 16px 22px; background: var(--surface-soft); border-bottom: 1px solid var(--line); }
.config-toolbar label { min-width: 220px; flex: 0 1 320px; }
.config-toolbar span { color: var(--muted); font-size: 12px; }
.connection-grid, .field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.connection-grid, .key-list, .config-panel > .field-grid, .config-panel > .filter-groups { margin-left: 22px; margin-right: 22px; }
.connection-grid, .config-panel > .field-grid:first-of-type { margin-top: 20px; }
.config-panel > .field-grid:last-child, .key-list { margin-bottom: 22px; }
label { display: grid; gap: 5px; color: #32453d; font-size: 12px; font-weight: 600; }
input:not([type='checkbox']), textarea, select { width: 100%; box-sizing: border-box; border: 1px solid #cad8d1; border-radius: 8px; padding: 8px 10px; background: #fff; color: #1e3028; font: inherit; font-size: 13px; }
input:focus, textarea:focus, select:focus { outline: 2px solid #bce1d2; border-color: #176b55; }
.connection-help { border-radius: 12px; background: #f6f8f7; padding: 14px; display: grid; gap: 5px; color: #617069; }
.connection-help strong { color: #20342b; }
.secret-box { margin: 16px 22px 0; padding: 14px; display: grid; grid-template-columns: 1fr minmax(240px, 2fr) auto; align-items: center; gap: 12px; border: 1px solid #e8c881; background: #fff9e9; border-radius: 12px; }
.secret-box div { display: grid; }.secret-box span { color: #786439; }.secret-box code { overflow-wrap: anywhere; }
.key-list { margin-top: 16px; display: grid; gap: 8px; }
.key-row { display: grid; grid-template-columns: 1fr auto auto; align-items: center; gap: 12px; padding: 12px; border: 1px solid #e2eae6; border-radius: 11px; }
.key-row div { display: grid; }.key-row span { color: #708078; }
.status-ready { color: #176b55 !important; }.status-muted { color: #9b6f6f !important; }
.wide { grid-column: 1 / -1; }
fieldset { border: 1px solid #dce7e1; border-radius: 9px; padding: 8px 11px; min-width: 0; }
legend { padding: 0 5px; font-size: 13px; font-weight: 700; color: #2b4037; }
.choice { display: inline-flex; align-items: center; gap: 5px; margin: 3px 12px 3px 0; font-size: 12px; font-weight: 500; }
.choice input { accent-color: var(--brand); }
.filter-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; margin-bottom: 14px; }
.plan-grid { padding-top: 18px; border-top: 1px solid #e5ece8; }
.run-list { display: grid; gap: 0; }.run-card { min-width: 0; border-top: 1px solid var(--line); background: #fff; }
.run-card:first-child { border-top: 0; }
.run-card-current { background: #f5faf7; }
.run-card-open { background: var(--brand-soft); }
.run-summary { width: 100%; display: grid; grid-template-columns: minmax(150px, 1.5fr) minmax(90px, .6fr) minmax(150px, 1fr) auto 18px; align-items: center; gap: 12px; padding: 13px 22px; border: 0; background: transparent; text-align: left; cursor: pointer; font-size: 12px; }
.run-summary:hover { background: rgba(23, 107, 85, .05); }
.run-summary:focus-visible { outline: 2px solid var(--brand); outline-offset: -3px; }
.run-identity { min-width: 0; display: grid; gap: 2px; }
.run-identity strong { color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.run-identity small, .run-count { color: var(--muted); font-size: 11px; }
.run-count strong { color: var(--brand-deep); font-size: 13px; }
.run-chevron { color: var(--muted); font-size: 18px; line-height: 1; }
.run-expanded { padding: 0 22px 14px; }
.run-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.run-head > div { display: flex; align-items: center; gap: 10px; }
.run-label { color: #65917b; font-size: 11px; font-weight: 700; letter-spacing: .08em; }
.run-status { padding: 5px 10px; border-radius: 999px; background: #e4f4eb; color: #176b55; font-size: 12px; font-weight: 700; white-space: nowrap; }
.run-status-failed, .run-status-uncertain { background: #fff0eb; color: #a34f38; }
.run-status-stopped, .run-status-paused { background: #f0f2f1; color: #63746b; }
.run-progress-heading { display: flex; align-items: baseline; justify-content: space-between; margin-top: 4px; color: #50675a; font-size: 11px; }
.run-progress-heading strong { color: #174b38; font-size: 22px; line-height: 1; }.run-progress-heading small { color: #8aa296; font-size: 13px; }
.progress-track { height: 6px; margin: 7px 0 12px; border-radius: 99px; background: #e8f1eb; overflow: hidden; }
.progress-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #2b9470, #75c6a1); transition: width .35s ease; }
.metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; margin-bottom: 10px; }
.metrics span { display: flex; align-items: baseline; gap: 5px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.metrics strong { color: #214e3a; font-size: 14px; }.metrics small { color: #71867a; font-size: 11px; }
.empty-copy { color: #77867f; }
.run-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 13px; border-top: 1px solid #ecf1ed; }
.run-footer small { min-width: 0; color: #73877b; overflow-wrap: anywhere; }
.step-panel { padding: 18px 22px; border-top: 1px solid var(--line); }.step-panel h4 { margin: 0; }
.step-card { padding: 13px; margin-top: 10px; border: 1px solid #e2eae6; border-radius: 10px; }.step-card p { margin: 7px 0; color: #55685f; }
.step-card blockquote { margin: 8px 0 0; padding: 10px 12px; border-left: 3px solid #2a8b6f; background: #f3f9f6; }.step-error { color: #b34444; }
@media (max-width: 860px) { .connection-grid, .field-grid, .filter-groups { grid-template-columns: 1fr; }.wide { grid-column: auto; }.secret-box { grid-template-columns: 1fr; }.run-summary { grid-template-columns: minmax(140px, 1fr) auto auto; }.run-summary .run-count:nth-of-type(3) { display: none; }.metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 600px) { .notice-card { padding: 18px; }.codex-delivery-view .panel-heading { padding: 16px 18px; align-items: flex-start; }.progress-title h3 { font-size: 18px; }.progress-empty { align-items: flex-start; flex-direction: column; gap: 12px; margin: 16px 18px; padding: 16px; }.run-summary { grid-template-columns: minmax(110px, 1fr) auto 18px; gap: 7px; padding: 12px 18px; }.run-summary .run-count { display: none; }.run-expanded { padding: 0 18px 14px; }.config-toolbar { padding: 14px 18px; }.connection-grid, .key-list, .config-panel > .field-grid, .config-panel > .filter-groups { margin-left: 18px; margin-right: 18px; }.secret-box { margin-left: 18px; margin-right: 18px; }.step-panel { padding: 16px 18px; }.metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.run-footer { align-items: flex-start; flex-direction: column; }.run-footer .ant-btn { align-self: flex-end; } }
@media (prefers-reduced-motion: reduce) { .progress-track span { transition: none; } }
</style>
