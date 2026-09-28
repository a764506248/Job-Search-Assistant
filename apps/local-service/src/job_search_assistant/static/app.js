const state = { jobs: [], filter: '', libraries: {}, templates: [], sampleResume: null, selectedTemplate: null }
const pageTitles = { overview: '工作台', jobs: '职位快照', profile: '个人档案', projects: '项目库', resumes: '简历库', templates: '简历模板', rules: '匹配规则', models: '模型配置', knowledge: '向量知识库' }
const routeByView = { overview: '/', jobs: '/jobs', profile: '/profile', projects: '/projects', resumes: '/resumes', templates: '/templates', rules: '/rules', models: '/models', knowledge: '/knowledge' }
const viewByRoute = Object.fromEntries(Object.entries(routeByView).map(([view, route]) => [route, view]))

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
  if (!pageTitles[name]) name = 'overview'
  $$('.view').forEach((node) => node.classList.toggle('active-view', node.id === `${name}-view`))
  $$('.nav-item[data-view]').forEach((node) => {
    const active = node.dataset.view === name
    node.classList.toggle('active', active)
    if (active) node.setAttribute('aria-current', 'page')
    else node.removeAttribute('aria-current')
  })
  $('#page-title').textContent = pageTitles[name] || '工作台'
  document.title = `${pageTitles[name]} · Job Search Assistant`
  if (name === 'profile') void loadProfile()
  if (name === 'knowledge') void Promise.all([loadRagStatus(), loadRagChunks()])
  if (name === 'templates') void loadTemplates()
  if ($(`#${name}-view`)?.classList.contains('library-view')) void loadLibrary(name)
}

function viewFromLocation() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return viewByRoute[path] || 'overview'
}

function navigateToView(name, { replace = false } = {}) {
  const view = pageTitles[name] ? name : 'overview'
  const route = routeByView[view]
  if (window.location.pathname !== route) {
    window.history[replace ? 'replaceState' : 'pushState']({ view }, '', route)
  }
  showView(view)
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
  $('#embedding-model').textContent = status.model || status.embeddingService?.model || 'jinaai/jina-embeddings-v2-base-zh'
  $('#rag-sources').textContent = String(status.sources)
  $('#rag-chunks').textContent = String(status.chunks)
  $('#rag-indexed-at').textContent = status.indexedAt ? `最后构建：${formatTime(status.indexedAt)}` : '尚未建立索引'
}

function sourceTypeLabel(value) {
  return ({ profile: '个人档案', projects: '项目库', resumes: '简历库' })[value] || value
}

async function loadRagChunks() {
  const container = $('#rag-chunk-list')
  container.innerHTML = '<div class="library-empty">正在读取本地向量数据…</div>'
  try {
    const response = await fetch('/v1/rag/chunks')
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || '无法读取向量数据')
    $('#rag-data-count').textContent = `${result.total} 个分片`
    container.innerHTML = result.items.length ? result.items.map((item) => {
      const vectorPreview = item.embedding.slice(0, 8).map((value) => Number(value).toFixed(4)).join(', ')
      return `
        <article class="vector-record">
          <div class="vector-record-head">
            <span class="tag">${escapeHtml(sourceTypeLabel(item.sourceType))}</span>
            <strong>${escapeHtml(item.sourceName)}</strong>
            <span class="vector-chip">分片 #${item.chunkIndex + 1}</span>
            <span class="vector-chip">${item.dimensions} 维</span>
          </div>
          <p>${escapeHtml(item.content)}</p>
          <details>
            <summary>查看向量信息</summary>
            <dl>
              <div><dt>模型</dt><dd>${escapeHtml(item.model)}</dd></div>
              <div><dt>向量预览</dt><dd>[${vectorPreview}${item.dimensions > 8 ? ', …' : ''}]</dd></div>
              <div><dt>内容哈希</dt><dd>${escapeHtml(item.contentHash)}</dd></div>
              <div><dt>索引时间</dt><dd>${escapeHtml(formatTime(item.indexedAt))}</dd></div>
            </dl>
          </details>
        </article>`
    }).join('') : '<div class="library-empty">向量库还没有数据，请先点击“重建本地索引”。</div>'
  } catch (error) {
    $('#rag-data-count').textContent = '读取失败'
    container.innerHTML = `<div class="library-empty">${escapeHtml(error.message)}</div>`
  }
}

function renderResumePreview() {
  const templateId = state.selectedTemplate || state.templates[0]?.id
  if (!templateId) return
  const container = $('#resume-preview')
  const frame = document.createElement('iframe')
  frame.className = 'resume-preview-frame'
  frame.title = '简历模板连续预览'
  frame.src = `/v1/resume-templates/${encodeURIComponent(templateId)}/sample`
  frame.scrolling = 'no'

  const fitPreviewHeight = () => {
    const documentElement = frame.contentDocument?.documentElement
    const body = frame.contentDocument?.body
    const height = Math.max(
      documentElement?.scrollHeight || 0,
      documentElement?.offsetHeight || 0,
      body?.scrollHeight || 0,
      body?.offsetHeight || 0,
    )
    if (height > 0) frame.style.height = `${height}px`
  }

  frame.addEventListener('load', () => {
    fitPreviewHeight()
    window.setTimeout(fitPreviewHeight, 120)
  })
  container.replaceChildren(frame)
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
        <button class="icon-button" data-match-id="${job.id}" type="button">自动匹配</button>
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
  navigateToView(viewFromLocation(), { replace: true })
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

$$('.nav-item[data-view]').forEach((button) => button.addEventListener('click', () => navigateToView(button.dataset.view)))
$$('[data-open-jobs]').forEach((button) => button.addEventListener('click', () => navigateToView('jobs')))
window.addEventListener('popstate', () => showView(viewFromLocation()))
$('#refresh-button').addEventListener('click', async () => {
  const active = $('.view.active-view')
  try {
    if (active?.classList.contains('library-view')) await loadLibrary(active.dataset.kind)
    else if (active?.id === 'profile-view') await loadProfile()
    else if (active?.id === 'knowledge-view') await Promise.all([loadRagStatus(), loadRagChunks()])
    else if (active?.id === 'templates-view') await loadTemplates()
    else await loadJobs()
    showToast('数据已刷新')
  } catch (error) { showToast(error.message) }
})
$('#job-search').addEventListener('input', (event) => { state.filter = event.target.value; renderJobs() })
$('#jobs-table-body').addEventListener('click', async (event) => {
  const matchButton = event.target.closest('[data-match-id]')
  if (matchButton) {
    const job = state.jobs.find((item) => item.id === Number(matchButton.dataset.matchId))
    if (!job) return
    const panel = $('#job-match-result')
    panel.hidden = false
    panel.innerHTML = '<div class="library-empty">正在执行规则分析、关键词召回和向量检索…</div>'
    try {
      const response = await fetch('/v1/jobs/match', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: job.title, jobText: job.description, skills: job.skills || [] }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || '自动匹配失败')
      const strategy = ({ custom: '定制简历 + 定制问候语', default: '默认简历 + 默认问候语', blocked: '不投递' })[result.decision.materialStrategy]
      panel.innerHTML = `
        <div class="panel-heading"><div><p class="eyebrow">LOCAL MATCH</p><h2>${escapeHtml(job.title)} · ${escapeHtml(job.companyName)}</h2></div><button class="icon-button" data-close-match type="button">关闭</button></div>
        <div class="match-metrics"><div><span>岗位适合度</span><strong>${result.suitabilityScore}</strong></div><div><span>定制可信度</span><strong>${result.customizationConfidence}</strong></div><div><span>材料策略</span><strong>${escapeHtml(strategy)}</strong></div></div>
        <div class="match-evidence"><h3>检索证据</h3>${result.evidence.slice(0, 5).map((item) => `<article><div><strong>${escapeHtml(item.sourceName)}</strong><span>综合 ${(item.score * 100).toFixed(1)}% · 向量 ${(item.vectorScore * 100).toFixed(1)}% · 关键词 ${(item.keywordScore * 100).toFixed(1)}%</span></div><p>${escapeHtml(item.content)}</p></article>`).join('') || '<p>暂无知识库证据，将使用默认材料。</p>'}</div>`
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (error) { panel.innerHTML = `<div class="library-empty">${escapeHtml(error.message)}</div>` }
    return
  }
  const button = event.target.closest('[data-delete-id]')
  if (!button || !window.confirm('确定删除这条职位快照吗？此操作不会影响 Boss 上的数据。')) return
  const response = await fetch(`/v1/jobs/${button.dataset.deleteId}`, { method: 'DELETE' })
  if (!response.ok) return showToast('删除失败')
  await loadJobs()
  showToast('职位快照已删除')
})

$('#job-match-result').addEventListener('click', (event) => {
  if (event.target.closest('[data-close-match]')) event.currentTarget.hidden = true
})

$('#profile-form').addEventListener('submit', async (event) => {
  event.preventDefault()
  const data = Object.fromEntries(new FormData(event.currentTarget))
  const response = await fetch('/v1/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data }) })
  showToast(response.ok ? '个人档案已保存' : '保存失败')
})

$('#resume-import-form').addEventListener('submit', async (event) => {
  event.preventDefault()
  const form = event.currentTarget
  const button = form.querySelector('button[type="submit"]')
  const resultBox = $('#resume-import-result')
  button.disabled = true
  button.textContent = '正在解析并入库…'
  resultBox.hidden = true
  try {
    const response = await fetch('/v1/resumes/import', { method: 'POST', body: new FormData(form) })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || '简历导入失败')
    const indexMessage = result.indexRebuilt
      ? `已重建 ${result.indexedChunks} 个向量分片`
      : `资料已入库，向量索引未重建：${result.indexError || 'Embedding 服务不可用'}`
    resultBox.innerHTML = `<strong>${escapeHtml(result.filename)} 导入成功</strong><br>个人档案更新 ${result.profileFields.length} 个字段，新增 ${result.projectIds.length} 条项目、1 条简历资料，提取 ${result.extractedCharacters} 个字符。${escapeHtml(indexMessage)}`
    resultBox.hidden = false
    form.reset()
    await Promise.all([loadLibrary('resumes'), loadProfile()])
    showToast('简历已解析并分别写入本地资料库')
  } catch (error) {
    resultBox.textContent = error.message
    resultBox.hidden = false
  } finally {
    button.disabled = false
    button.textContent = '解析并直接入库'
  }
})

$('#rebuild-index').addEventListener('click', async (event) => {
  const button = event.currentTarget
  button.disabled = true
  button.textContent = '正在生成向量…'
  try {
    const response = await fetch('/v1/rag/rebuild', { method: 'POST' })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || '索引构建失败')
    await Promise.all([loadRagStatus(), loadRagChunks()])
    showToast(`已生成 ${result.rebuilt} 个本地向量分片`)
  } catch (error) { showToast(error.message) }
  finally { button.disabled = false; button.textContent = '重建本地索引' }
})

$('#refresh-rag-data').addEventListener('click', () => void loadRagChunks())

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
        <span class="rag-score">综合 ${(item.score * 100).toFixed(1)}% · 向量 ${(item.vectorScore * 100).toFixed(1)}% · 关键词 ${(item.keywordScore * 100).toFixed(1)}%</span>
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
