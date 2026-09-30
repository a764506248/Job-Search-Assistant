<template>
  <div class="view active-view">
    <div class="toolbar panel">
      <label class="search-field"><span aria-hidden="true">⌕</span><input v-model="filter" type="search" placeholder="搜索职位、公司、技能或 JD 内容" /></label>
      <label class="snapshot-result-filter"><span>沟通结果</span><select v-model="communicationResult"><option value="">全部</option><option value="not_communicated">未沟通</option><option value="communicated">已沟通</option><option value="interviewed">已获得面试</option></select></label>
      <span class="result-count">显示 {{ jobs.length }} / {{ total }} 条</span>
      <a-button type="primary" @click="showCreate = !showCreate">{{ showCreate ? '收起表单' : '手动添加职位' }}</a-button>
    </div>

    <section v-if="showCreate" class="panel job-create-panel">
      <div class="panel-heading"><div><p class="eyebrow">MANUAL SNAPSHOT</p><h2>手动添加职位快照</h2></div></div>
      <form class="data-form job-create-form" @submit.prevent="createJob">
        <div class="form-row"><label>职位名称<input v-model.trim="form.title" required placeholder="例如：AI Agent 工程师" /></label><label>公司名称<input v-model.trim="form.companyName" required placeholder="例如：未来智能科技" /></label></div>
        <label>公司规模<input v-model.trim="form.companySize" placeholder="例如：100-499人" /></label>
        <div class="form-row"><label>薪资<input v-model.trim="form.salaryText" placeholder="25-40K·14薪" /></label><label>城市 / 区域<input v-model.trim="form.location" placeholder="北京·丰台区" /></label></div>
        <label>详细工作地址<input v-model.trim="form.workAddress" placeholder="例如：北京市丰台区汉威国际广场四区 1 号楼 7 层" /></label>
        <div class="form-row"><label>经验要求<input v-model.trim="form.experience" placeholder="3-5年" /></label><label>学历要求<input v-model.trim="form.education" placeholder="本科" /></label></div>
        <label>职位链接<input v-model.trim="form.url" type="url" placeholder="https://www.zhipin.com/job_detail/..." /></label>
        <label>技能标签<input v-model.trim="form.skillsText" placeholder="Python, FastAPI, LangGraph, RAG" /></label>
        <div class="form-row"><label>招聘者姓名<input v-model.trim="form.recruiterName" placeholder="李女士" /></label><label>招聘者职位<input v-model.trim="form.recruiterTitle" placeholder="招聘经理" /></label></div>
        <label>完整 JD<textarea v-model.trim="form.description" required rows="8" placeholder="岗位职责、任职要求、加分项等完整职位描述"></textarea></label>
        <div class="form-actions"><a-button type="primary" html-type="submit" :loading="creating">保存职位快照</a-button><a-button @click="resetForm">清空</a-button></div>
      </form>
    </section>

    <a-modal v-model:open="detailOpen" width="980px" wrap-class-name="snapshot-detail-modal" :footer="null" centered destroy-on-close @after-close="closeDetail">
      <template #title><div v-if="detailJob" class="snapshot-modal-title"><strong>{{ detailJob.title }}</strong><span>{{ detailJob.companyName }} · {{ detailJob.companySize || '公司规模未识别' }}</span></div></template>
      <div v-if="detailJob" class="job-detail-modal-body">
        <div class="snapshot-test-actions"><div><strong>材料生成测试</strong><span>读取当前 JD、个人档案、向量证据、默认问候语和默认简历；仅生成预览，不会发送或覆盖数据。</span></div><a-button class="material-test-button" type="primary" :loading="previewing" @click="generateMaterialPreview">{{ previewing ? '正在生成材料…' : '生成材料示例' }}</a-button></div>
        <div class="snapshot-detail-grid"><div><span>薪资</span><strong>{{ detailJob.salaryText || '未识别' }}</strong></div><div><span>城市 / 区域</span><strong>{{ detailJob.location || '未识别' }}</strong></div><div><span>详细工作地址</span><strong>{{ detailJob.workAddress || '未识别' }}</strong></div><div><span>经验</span><strong>{{ detailJob.experience || '未识别' }}</strong></div><div><span>学历</span><strong>{{ detailJob.education || '未识别' }}</strong></div><div><span>招聘者</span><strong>{{ [detailJob.recruiterName, detailJob.recruiterTitle].filter(Boolean).join(' · ') || '未识别' }}</strong></div><div><span>采集时间</span><strong>{{ formatTime(detailJob.capturedAt) }}</strong></div></div>
        <div v-if="detailJob.skills?.length" class="snapshot-detail-tags"><span v-for="tag in detailJob.skills" :key="tag" class="tag">{{ tag }}</span></div>
        <section class="snapshot-jd"><h3>完整 JD</h3><pre>{{ detailJob.description }}</pre></section>
        <section class="snapshot-material"><h3>投递材料与结果</h3><dl><div><dt>沟通</dt><dd>{{ detailJob.hasCommunicated ? '已沟通' : '未沟通' }}</dd></div><div><dt>面试</dt><dd>{{ detailJob.hasInterview ? '已获得面试' : '暂无面试' }}</dd></div><div><dt>简历</dt><dd>{{ detailJob.resumeVariant === 'optimized' ? '针对 JD 优化简历' : '默认简历' }}{{ detailJob.generatedResumeId ? ` · ID ${detailJob.generatedResumeId}` : '' }}</dd></div><div><dt>问候语</dt><dd>{{ detailJob.generatedGreeting || '尚未生成或记录' }}</dd></div><div><dt>优化说明</dt><dd>{{ detailJob.resumeOptimization || '暂无' }}</dd></div></dl></section>
        <section v-if="materialPreview" class="material-preview"><div class="material-preview-heading"><div><h3>生成示例</h3><p>{{ materialPreview.modelName }} · {{ materialPreview.modelId }}</p></div><div><span>适合度 {{ materialPreview.match.suitabilityScore }}</span><span>可信度 {{ materialPreview.match.customizationConfidence }}</span></div></div><article><h4>新问候语</h4><p>{{ materialPreview.greeting }}</p><details><summary>查看默认问候语</summary><p>{{ materialPreview.defaultGreeting || '未配置默认问候语' }}</p></details></article><article><h4>{{ materialPreview.resume.headline }}</h4><div v-for="section in resumePreviewSections" :key="section.title" class="resume-preview-section"><strong>{{ section.title }}</strong><ul><li v-for="item in section.items" :key="item">{{ item }}</li></ul></div></article><article><h4>采用的向量证据</h4><ul><li v-for="item in materialPreview.match.evidence.slice(0, 5)" :key="`${item.sourceId}-${item.chunkIndex}`"><strong>{{ item.sourceName }}</strong> · {{ item.content }}</li></ul></article></section>
      </div>
    </a-modal>

    <section v-if="match" class="panel match-result">
      <div class="panel-heading"><div><p class="eyebrow">LOCAL MATCH</p><h2>{{ match.job.title }} · {{ match.job.companyName }}</h2></div><a-button size="small" @click="match = null">关闭</a-button></div>
      <div class="match-metrics">
        <div><span>岗位适合度</span><strong>{{ match.result.suitabilityScore }}</strong></div>
        <div><span>定制可信度</span><strong>{{ match.result.customizationConfidence }}</strong></div>
        <div><span>材料策略</span><strong>{{ strategyLabel(match.result.decision.materialStrategy) }}</strong></div>
      </div>
      <div class="match-evidence"><h3>检索证据</h3>
        <article v-for="item in match.result.evidence.slice(0, 5)" :key="`${item.sourceId}-${item.chunkIndex}`">
          <div><strong>{{ item.sourceName }}</strong><span>综合 {{ percent(item.score) }} · 向量 {{ percent(item.vectorScore) }} · 关键词 {{ percent(item.keywordScore) }}</span></div><p>{{ item.content }}</p>
        </article>
        <p v-if="!match.result.evidence.length">暂无知识库证据，将使用默认材料。</p>
      </div>
    </section>

    <a-modal v-model:open="trackingOpen" width="720px" wrap-class-name="job-tracking-modal" :footer="null" centered destroy-on-close @after-close="closeTracking">
      <template #title><div v-if="editingJob" class="snapshot-modal-title"><strong>{{ editingJob.title }} · 投递跟进</strong><span>{{ editingJob.companyName }}</span></div></template>
      <form v-if="editingJob" class="data-form job-tracking-form" @submit.prevent="saveTracking">
        <div class="tracking-switches"><label><input v-model="trackingForm.hasCommunicated" type="checkbox" /> 已产生沟通</label><label><input v-model="trackingForm.hasInterview" type="checkbox" /> 已获得面试</label></div>
        <label>生成的问候语<textarea v-model.trim="trackingForm.generatedGreeting" rows="3" placeholder="保存实际生成或发送给招聘者的问候语"></textarea></label>
        <div class="form-row"><label>投递简历类型<select v-model="trackingForm.resumeVariant"><option value="default">默认简历</option><option value="optimized">针对 JD 优化简历</option></select></label><label>关联简历 ID<input v-model.number="trackingForm.generatedResumeId" type="number" min="1" placeholder="简历库记录 ID" /></label></div>
        <label>简历优化说明<textarea v-model.trim="trackingForm.resumeOptimization" rows="4" placeholder="例如：突出 LangGraph、RAG、FastAPI 项目，弱化与 JD 无关经历"></textarea></label>
        <div class="form-actions"><a-button @click="trackingOpen = false">取消</a-button><a-button type="primary" html-type="submit" :loading="savingTracking">保存跟进数据</a-button></div>
      </form>
    </a-modal>

    <section class="panel table-panel">
      <div v-if="loading" class="library-empty">正在读取职位数据…</div>
      <div v-else-if="!jobs.length" class="empty-state"><span class="empty-icon">▤</span><h3>{{ filter ? '没有匹配的职位' : '还没有职位数据' }}</h3><p>{{ filter ? '请调整搜索关键词后重试。' : '打开 Boss 职位详情页后，扩展会自动将 JD 保存到这里。' }}</p></div>
      <div v-else class="table-wrap"><table><thead><tr><th>职位与公司</th><th>薪资 / 地点</th><th>要求</th><th><span class="field-heading">生成问候语<small>generatedGreeting</small></span></th><th>沟通结果</th><th>采集时间</th><th>操作</th></tr></thead>
        <tbody><tr v-for="job in jobs" :key="job.id">
          <td><strong>{{ job.title }}</strong><small>{{ job.companyName }}</small><small>{{ job.companySize || '规模未识别' }}</small></td>
          <td><strong>{{ job.salaryText || '—' }}</strong><small>{{ job.location || '地点未识别' }}</small><small v-if="job.workAddress" class="job-address-preview">{{ job.workAddress }}</small></td>
          <td><div class="tags"><span v-for="tag in jobTags(job)" :key="tag" class="tag">{{ tag }}</span></div></td>
          <td><div class="job-greeting-cell"><span :class="['greeting-status', { ready: Boolean(job.generatedGreeting) }]">{{ job.generatedGreeting ? '已生成' : '未生成' }}</span><p class="job-greeting-preview" :title="job.generatedGreeting || '当前快照尚未生成问候语'">{{ job.generatedGreeting || '当前快照尚未生成问候语' }}</p></div></td>
          <td><div class="snapshot-outcomes"><span :class="job.hasCommunicated ? 'outcome-positive' : ''">{{ job.hasCommunicated ? '已沟通' : '未沟通' }}</span><span :class="job.hasInterview ? 'outcome-positive' : ''">{{ job.hasInterview ? '有面试' : '无面试' }}</span><small>{{ job.resumeVariant === 'optimized' ? '优化简历' : '默认简历' }}</small></div></td>
          <td><time>{{ formatTime(job.capturedAt) }}</time><br><small>{{ sourceLabel(job.source) }}</small></td>
          <td><div class="row-actions"><a-button type="primary" ghost size="small" @click="openDetail(job)">查看详情</a-button><a-button size="small" @click="editTracking(job)">跟进</a-button><a-button size="small" :loading="matchingId === job.id" @click="runMatch(job)">自动匹配</a-button><a-button size="small" :href="job.url" target="_blank">打开</a-button><a-button size="small" danger @click="confirmDelete(job)">删除</a-button></div></td>
        </tr></tbody>
      </table></div>
      <div v-if="total" class="snapshot-pagination"><a-pagination v-model:current="page" v-model:page-size="pageSize" :total="total" :show-size-changer="true" :page-size-options="['10', '20', '50', '100']" show-quick-jumper :show-total="(value: number) => `共 ${value} 条职位快照`" @change="changePage" @show-size-change="changePageSize" /></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import { formatTime } from '../../utils/format'
import type { JobMatch, JobTrackingUpdate, MaterialPreview, StoredJob } from '../../types'

const jobs = ref<StoredJob[]>([])
const filter = ref('')
const communicationResult = ref('')
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const matchingId = ref<number | null>(null)
const match = ref<{ job: StoredJob; result: JobMatch } | null>(null)
const showCreate = ref(false)
const creating = ref(false)
const editingJob = ref<StoredJob | null>(null)
const trackingOpen = ref(false)
const savingTracking = ref(false)
const detailJob = ref<StoredJob | null>(null)
const detailOpen = ref(false)
const previewing = ref(false)
const materialPreview = ref<MaterialPreview | null>(null)
const trackingForm = reactive<JobTrackingUpdate>({ hasCommunicated: false, hasInterview: false, generatedGreeting: '', resumeVariant: 'default', generatedResumeId: undefined, resumeOptimization: '' })
const emptyForm = () => ({ title: '', companyName: '', companySize: '', url: '', location: '', workAddress: '', salaryText: '', experience: '', education: '', description: '', skillsText: '', recruiterName: '', recruiterTitle: '' })
const form = reactive(emptyForm())
const resumePreviewSections = computed(() => materialPreview.value ? [
  { title: '个人优势', items: materialPreview.value.resume.summary },
  { title: '技术栈', items: materialPreview.value.resume.skills },
  { title: '项目经历', items: materialPreview.value.resume.projects },
  { title: '工作经历', items: materialPreview.value.resume.workExperience },
  { title: '教育经历', items: materialPreview.value.resume.education },
  { title: '编排说明', items: materialPreview.value.resume.optimizationNotes },
].filter((section) => section.items.length) : [])

const percent = (value: number) => `${(value * 100).toFixed(1)}%`
const strategyLabel = (value: string) => ({ custom: '定制简历 + 定制问候语', default: '默认简历 + 默认问候语', blocked: '不投递' } as Record<string, string>)[value] || value
const jobTags = (job: StoredJob) => [job.experience, job.education, ...(job.skills || []).slice(0, 4)].filter(Boolean) as string[]
const sourceLabel = (source: StoredJob['source']) => ({ dom: '页面采集', 'page-state': '页面数据', manual: '手动添加' })[source]

function resetForm() { Object.assign(form, emptyForm()) }
async function createJob() {
  creating.value = true
  try {
    await api.createJob({
      title: form.title,
      companyName: form.companyName,
      companySize: form.companySize || undefined,
      url: form.url || undefined,
      location: form.location || undefined,
      workAddress: form.workAddress || undefined,
      salaryText: form.salaryText || undefined,
      experience: form.experience || undefined,
      education: form.education || undefined,
      description: form.description,
      skills: form.skillsText.split(/[,，/|]/).map((item) => item.trim()).filter(Boolean),
      recruiterName: form.recruiterName || undefined,
      recruiterTitle: form.recruiterTitle || undefined,
    })
    resetForm()
    showCreate.value = false
    await load()
    message.success('职位快照已保存')
  } catch (error) { message.error((error as Error).message) }
  finally { creating.value = false }
}

function openDetail(job: StoredJob) {
  detailJob.value = job
  materialPreview.value = null
  detailOpen.value = true
}

function closeDetail() { detailJob.value = null; materialPreview.value = null }
async function generateMaterialPreview() {
  if (!detailJob.value) return
  previewing.value = true
  try { materialPreview.value = await api.previewJobMaterials(detailJob.value.id); message.success('材料示例生成完成') }
  catch (error) { message.error((error as Error).message) }
  finally { previewing.value = false }
}

async function load() {
  loading.value = true
  try {
    const result = await api.jobs({ page: page.value, pageSize: pageSize.value, query: filter.value, communicationResult: communicationResult.value })
    jobs.value = result.items
    total.value = result.total
    page.value = result.page
  }
  catch (error) { message.error((error as Error).message) }
  finally { loading.value = false }
}

function changePage(nextPage: number) { page.value = nextPage; void load() }
function changePageSize(_current: number, nextSize: number) { page.value = 1; pageSize.value = nextSize; void load() }

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(filter, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; void load() }, 300)
})
watch(communicationResult, () => { page.value = 1; void load() })
onBeforeUnmount(() => { if (searchTimer) clearTimeout(searchTimer) })

async function runMatch(job: StoredJob) {
  matchingId.value = job.id
  try { match.value = { job, result: await api.matchJob(job) } }
  catch (error) { message.error((error as Error).message) }
  finally { matchingId.value = null }
}

function editTracking(job: StoredJob) {
  editingJob.value = job
  Object.assign(trackingForm, {
    hasCommunicated: job.hasCommunicated,
    hasInterview: job.hasInterview,
    generatedGreeting: job.generatedGreeting || '',
    resumeVariant: job.resumeVariant || 'default',
    generatedResumeId: job.generatedResumeId,
    resumeOptimization: job.resumeOptimization || '',
  })
  trackingOpen.value = true
}

function closeTracking() { editingJob.value = null }

async function saveTracking() {
  if (!editingJob.value) return
  savingTracking.value = true
  try {
    await api.updateJobTracking(editingJob.value.id, {
      ...trackingForm,
      generatedResumeId: trackingForm.generatedResumeId || undefined,
      generatedGreeting: trackingForm.generatedGreeting || undefined,
      resumeOptimization: trackingForm.resumeOptimization || undefined,
    })
    await load()
    trackingOpen.value = false
    message.success('投递跟进数据已保存')
  } catch (error) { message.error((error as Error).message) }
  finally { savingTracking.value = false }
}

function confirmDelete(job: StoredJob) {
  Modal.confirm({ title: '确定删除这条职位快照吗？', content: '此操作不会影响 Boss 上的数据。', okType: 'danger', async onOk() { await api.deleteJob(job.id); await load(); message.success('职位快照已删除') } })
}

useRefresh(load)
</script>
