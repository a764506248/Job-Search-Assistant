const state = { jobs: [], filter: '', libraries: {}, templates: [], sampleResume: null, selectedTemplate: null }
const pageTitles = { overview: '工作台', jobs: '职位快照', profile: '个人档案', projects: '项目库', resumes: '简历库', templates: '简历模板', rules: '匹配规则', models: '模型配置', knowledge: '向量知识库' }

const $ = (selector) => document.querySelector(selector)
const $$ = (selector) => document.querySelectorAll(selector)

function escapeHtml(value = '') {
  return value.replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char])
}

function formatTime(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(new Date(value))
}

function showToast(message) {
  const toast = $('#toast')
  toast.textContent = message
  toast.classList.add('show')
  window.setTimeout(() => toast.classList.remove('show'), 2400)
}

function showView(name) {
  $$('.view').forEach((node) => node.classList.toggle('active-view', node.id === `${name}-view`))
  $$('.nav-item[data-view]').forEach((node) => node.classList.toggle('active', node.dataset.view === name))
  $('#page-title').textContent = pageTitles[name] || '工作台'
  if (name === 'profile') void loadProfile()
  if (name === 'knowledge') void loadRagStatus()
  if (name === 'templates') void loadTemplates()
  if ($(`#${name}-view`)?.classList.contains('library-view')) void loadLibrary(name)
}

function displayData(kind, data) {
  if (kind === 'projects') return data.summary || data.repositoryUrl || '尚未填写项目说明'
  if (kind === 'resumes') return `${data.format || '未指定格式'} · ${data.notes || '暂无备注'}`
  if (kind === 'rules') return `${data.pattern || '未填写条件'} · ${actionLabel(data.action)}`
  if (kind === 'models') return `${data.provider || '未指定服务商'} · ${data.model || '未填写模型'}`
  return ''
}

function actionLabel(action) {
  return ({ notify: '仅提醒', reduce_score: '降低匹配分', use_default_materials: '使用默认材料继续投递', block_delivery: '禁止投递' })[action] || action || '未配置动作'
}

function renderLibrary(kind) {
  const view = $(`#${kind}-view`)
  const records = state.libraries[kind] || []
  view.querySelector('.library-count').textContent = `${records.length} 条记录`
  const grid = view.querySelector('.record-grid')
  if (!records.length) {
    grid.innerHTML = '<div class="library-empty">还没有数据，请使用左侧表单添加第一条记录。</div>'
    return
  }
  grid.innerHTML = records.map((record) => `
    <article class="record-card">
      <div class="record-card-head">
        <div><h3>${escapeHtml(record.name)}</h3><p>${escapeHtml(displayData(kind, record.data))}</p></div>
        <div class="record-actions"><button class="icon-button" data-edit-record="${record.id}" type="button">编辑</button><button class="icon-button danger" data-delete-record="${record.id}" type="button">删除</button></div>
      </div>
      ${record.data.tags ? `<div class="tags">${record.data.tags.split(',').map((tag) => `<span class="tag">${escapeHtml(tag.trim())}</span>`).join('')}</div>` : ''}
    </article>
  `).join('')
}

async function loadLibrary(kind) {
  const response = await fetch(`/v1/library/${kind}`)
  if (!response.ok) throw new Error('无法读取数据')
  state.libraries[kind] = (await response.json()).items
  renderLibrary(kind)
}

async function loadProfile() {
  const result = await fetch('/v1/profile').then((response) => response.json())
  const form = $('#profile-form')
  Object.entries(result.data || {}).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? ''
  })
}

async function loadRagStatus() {
  const response = await fetch('/v1/rag/status')
  if (!response.ok) throw new Error('无法读取索引状态')
  const status = await response.json()
  $('#embedding-status').textContent = status.embeddingAvailable ? '已连接' : '未启动'
  $('#embedding-status').className = status.embeddingAvailable ? 'status-good' : 'status-bad'
  $('#embedding-model').textContent = status.model || status.embeddingService?.model || 'BAAI/bge-small-zh-v1.5'
  $('#rag-sources').textContent = String(status.sources)
  $('#rag-chunks').textContent = String(status.chunks)
  $('#rag-indexed-at').textContent = status.indexedAt ? `最后构建：${formatTime(status.indexedAt)}` : '尚未建立索引'
}

function renderResumePreview() {
  const templateId = state.selectedTemplate || state.templates[0]?.id
  if (!templateId) return
  $('#resume-preview').innerHTML = `<iframe class="resume-preview-frame" title="简历模板预览" src="/v1/resume-templates/${encodeURIComponent(templateId)}/sample"></iframe>`
}

function renderTemplateList() {
  $('#template-list').innerHTML = state.templates.map((template) => `
    <article class="template-option ${state.selectedTemplate === template.id ? 'selected' : ''}">
      <div class="template-swatch" style="--template-accent:${escapeHtml(template.accent)}"><span></span><span></span><span></span></div>
      <div><h3>${escapeHtml(template.name)}</h3><p>${escapeHtml(template.description)}</p></div>
      <div class="template-buttons">
        <button class="button primary" data-select-template="${escapeHtml(template.id)}" type="button">${state.selectedTemplate === template.id ? '当前模板' : '选择模板'}</button>
        <a class="button ghost" href="/v1/resume-templates/${escapeHtml(template.id)}/sample.pdf" target="_blank">查看 PDF 示例</a>
      </div>
    </article>
  `).join('')
  const selected = state.templates.find((item) => item.id === state.selectedTemplate)
  $('#selected-template-label').textContent = selected ? selected.name : ''
}

async function loadTemplates() {
  const [templates, profile] = await Promise.all([
    fetch('/v1/resume-templates').then((response) => response.json()),
    fetch('/v1/profile').then((response) => response.json()),
  ])
  state.templates = templates.items
  state.sampleResume = templates.sampleData
  state.selectedTemplate = profile.data?.resumeTemplateId || templates.items[0]?.id
  renderTemplateList()
  renderResumePreview()
}

function resetRecordForm(form) {
  form.reset()
  form.elements.recordId.value = ''
  form.querySelector('.cancel-edit').hidden = true
  form.querySelector('[type="submit"]').textContent = form.closest('[data-kind]').dataset.kind === 'projects' ? '保存项目' : '保存记录'
}

function editRecord(kind, recordId) {
  const view = $(`#${kind}-view`)
  const form = view.querySelector('.record-form')
  const record = state.libraries[kind].find((item) => item.id === Number(recordId))
  if (!record) return
  form.elements.recordId.value = record.id
  form.elements.name.value = record.name
  Object.entries(record.data).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? '' })
  form.querySelector('.cancel-edit').hidden = false
  form.querySelector('[type="submit"]').textContent = '保存修改'
  form.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function saveRecord(kind, form) {
  const values = Object.fromEntries(new FormData(form))
  const recordId = values.recordId
  const name = values.name.trim()
  delete values.recordId
  delete values.name
  const response = await fetch(`/v1/library/${kind}${recordId ? `/${recordId}` : ''}`, {
    method: recordId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, data: values }),
  })
  if (!response.ok) throw new Error('保存失败')
  resetRecordForm(form)
  await loadLibrary(kind)
  showToast('数据已保存')
}

function renderOverview() {
  const companies = new Set(state.jobs.map((job) => job.companyName))
  const today = new Date().toDateString()
  const todayCount = state.jobs.filter((job) => new Date(job.capturedAt).toDateString() === today).length
  $('#metric-jobs').textContent = String(state.jobs.length)
  $('#metric-companies').textContent = String(companies.size)
  $('#metric-today').textContent = String(todayCount)

  const container = $('#recent-jobs')
  if (!state.jobs.length) {
    container.innerHTML = '<div class="empty-state"><span class="empty-icon">▤</span><h3>等待第一份 JD</h3><p>打开 Boss 职位详情页后，采集结果会出现在这里。</p></div>'
    return
  }
  container.innerHTML = state.jobs.slice(0, 5).map((job) => `
    <article class="job-row">
      <div><h3>${escapeHtml(job.title)}</h3><p>${escapeHtml(job.companyName)}</p></div>
      <span class="job-meta">${escapeHtml(job.salaryText || '薪资未识别')} · ${escapeHtml(job.location || '地点未识别')}</span>
      <time class="job-time">${formatTime(job.capturedAt)}</time>
    </article>
  `).join('')
}

function filteredJobs() {
  const query = state.filter.trim().toLowerCase()
  if (!query) return state.jobs
  return state.jobs.filter((job) => [
    job.title, job.companyName, job.description, job.location, ...(job.skills || [])
  ].filter(Boolean).join(' ').toLowerCase().includes(query))
}

function renderJobs() {
  const jobs = filteredJobs()
  $('#result-count').textContent = `显示 ${jobs.length} / ${state.jobs.length} 条`
  $('#jobs-empty').hidden = jobs.length > 0
  $('#jobs-table-body').innerHTML = jobs.map((job) => `
    <tr>
      <td><strong>${escapeHtml(job.title)}</strong><small>${escapeHtml(job.companyName)}</small></td>
      <td><strong>${escapeHtml(job.salaryText || '—')}</strong><small>${escapeHtml(job.location || '地点未识别')}</small></td>
      <td><div class="tags">
        ${[job.experience, job.education, ...(job.skills || []).slice(0, 4)].filter(Boolean).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join('') || '<span class="tag">待分析</span>'}
      </div></td>
      <td><time>${formatTime(job.capturedAt)}</time><br><small>${job.source === 'dom' ? '页面采集' : '页面数据'}</small></td>
      <td><div class="row-actions">
        <a class="icon-button" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">打开</a>
        <button class="icon-button danger" data-delete-id="${job.id}" type="button">删除</button>
      </div></td>
    </tr>
  `).join('')
}

async function loadJobs() {
  const response = await fetch('/v1/jobs?limit=500')
  if (!response.ok) throw new Error('无法读取职位数据')
  const result = await response.json()
  state.jobs = result.items
  renderOverview()
  renderJobs()
}

async function initialize() {
  try {
    const health = await fetch('/v1/health').then((response) => response.json())
    $('#service-dot').classList.add('online')
    $('#service-status').textContent = `本地服务 ${health.version}`
    await loadJobs()
  } catch (error) {
    $('#service-status').textContent = '本地服务连接失败'
    showToast(error.message || '数据加载失败')
  }
}

$$('.nav-item[data-view]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)))
$$('[data-open-jobs]').forEach((button) => button.addEventListener('click', () => showView('jobs')))
$('#refresh-button').addEventListener('click', async () => {
  const active = $('.view.active-view')
  try {
    if (active?.classList.contains('library-view')) await loadLibrary(active.dataset.kind)
    else if (active?.id === 'profile-view') await loadProfile()
    else await loadJobs()
    showToast('数据已刷新')
  } catch (error) { showToast(error.message) }
})
$('#job-search').addEventListener('input', (event) => { state.filter = event.target.value; renderJobs() })
$('#jobs-table-body').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-delete-id]')
  if (!button || !window.confirm('确定删除这条职位快照吗？此操作不会影响 Boss 上的数据。')) return
  const response = await fetch(`/v1/jobs/${button.dataset.deleteId}`, { method: 'DELETE' })
  if (!response.ok) return showToast('删除失败')
  await loadJobs()
  showToast('职位快照已删除')
})

$('#profile-form').addEventListener('submit', async (event) => {
  event.preventDefault()
  const data = Object.fromEntries(new FormData(event.currentTarget))
  const response = await fetch('/v1/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data }) })
  showToast(response.ok ? '个人档案已保存' : '保存失败')
})

$('#rebuild-index').addEventListener('click', async (event) => {
  const button = event.currentTarget
  button.disabled = true
  button.textContent = '正在生成向量…'
  try {
    const response = await fetch('/v1/rag/rebuild', { method: 'POST' })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || '索引构建失败')
    await loadRagStatus()
    showToast(`已生成 ${result.rebuilt} 个本地向量分片`)
  } catch (error) { showToast(error.message) }
  finally { button.disabled = false; button.textContent = '重建本地索引' }
})

$('#rag-search-form').addEventListener('submit', async (event) => {
  event.preventDefault()
  const query = new FormData(event.currentTarget).get('query')?.trim()
  if (!query) return
  const container = $('#rag-results')
  container.innerHTML = '<div class="library-empty">正在检索…</div>'
  try {
    const response = await fetch('/v1/rag/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit: 5 }),
    })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || '检索失败')
    container.innerHTML = result.items.length ? result.items.map((item) => `
      <article class="rag-result">
        <div><span class="tag">${escapeHtml(item.sourceType)}</span><strong>${escapeHtml(item.sourceName)}</strong></div>
        <span class="rag-score">相似度 ${(item.score * 100).toFixed(1)}%</span>
        <p>${escapeHtml(item.content)}</p>
      </article>
    `).join('') : '<div class="library-empty">没有检索到资料，请先重建索引。</div>'
  } catch (error) { container.innerHTML = `<div class="library-empty">${escapeHtml(error.message)}</div>` }
})

$('#template-list').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-select-template]')
  if (!button) return
  const profile = await fetch('/v1/profile').then((response) => response.json())
  const response = await fetch('/v1/profile', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: { ...(profile.data || {}), resumeTemplateId: button.dataset.selectTemplate } }),
  })
  if (!response.ok) return showToast('模板选择保存失败')
  state.selectedTemplate = button.dataset.selectTemplate
  renderTemplateList()
  showToast('已设为默认投递模板')
})

$$('.record-form').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    try { await saveRecord(form.closest('[data-kind]').dataset.kind, form) } catch (error) { showToast(error.message) }
  })
  form.querySelector('.cancel-edit').addEventListener('click', () => resetRecordForm(form))
})

$$('.record-grid').forEach((grid) => grid.addEventListener('click', async (event) => {
  const view = grid.closest('[data-kind]')
  const kind = view.dataset.kind
  const editButton = event.target.closest('[data-edit-record]')
  if (editButton) return editRecord(kind, editButton.dataset.editRecord)
  const deleteButton = event.target.closest('[data-delete-record]')
  if (!deleteButton || !window.confirm('确定删除这条本地记录吗？')) return
  const response = await fetch(`/v1/library/${kind}/${deleteButton.dataset.deleteRecord}`, { method: 'DELETE' })
  if (!response.ok) return showToast('删除失败')
  await loadLibrary(kind)
  showToast('记录已删除')
}))

void initialize()
