const state = { jobs: [], filter: '' }

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
  $('#page-title').textContent = name === 'jobs' ? '职位快照' : '工作台'
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
  try { await loadJobs(); showToast('数据已刷新') } catch (error) { showToast(error.message) }
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

void initialize()
