<template>
  <div class="view active-view automation-view">
    <section class="automation-command panel">
      <div><p class="eyebrow">AUTOMATION CONTROL</p><h2>自动投递任务</h2><p>创建时冻结可投岗位计划；启动后由 Docker 内置执行器通过统一扩展操作浏览器。</p></div>
      <label>每日目标<input v-model.number="targetCount" type="number" min="1" max="500" /></label>
      <a-button type="primary" :loading="creating" @click="createRun">创建任务</a-button>
    </section>
    <section class="automation-readiness panel">
      <div :class="{ ready: runnerReady }"><strong>执行器</strong><span>{{ runnerReady ? 'Docker 内置执行器在线' : '未在线，请重新启动 Docker 服务' }}</span></div>
      <div :class="{ ready: browser?.connected }"><strong>浏览器扩展</strong><span>{{ browser?.connected ? `已连接 · v${browser.extensionVersion || '-'}` : '未连接，请前往安装向导重新配对' }}</span></div>
      <div :class="{ ready: setup?.overall === 'ready' }"><strong>启动检查</strong><span>{{ setup?.overall === 'ready' ? '全部通过' : '存在阻塞项，启动任务时会停止并说明原因' }}</span></div>
    </section>
    <div class="automation-layout">
      <section class="panel automation-runs">
        <div class="panel-heading"><h2>任务记录</h2><a-button @click="load">刷新</a-button></div>
        <div v-if="!runs.length" class="library-empty">还没有自动投递任务。</div>
        <article v-for="run in runs" :key="run.id" :class="{ selected: selected?.id === run.id }" @click="selectRun(run)">
          <div><strong>#{{ run.id }} · {{ statusName(run.status) }}</strong><span>计划 {{ plannedCount(run) }} · 目标 {{ run.targetCount }} · 成功 {{ run.successCount }} · 失败 {{ run.failureCount }}</span><span>{{ run.runnerId ? `执行器 ${run.runnerId} · 心跳 ${run.heartbeatAt ? formatTime(run.heartbeatAt) : '等待中'}` : '尚未被执行器认领' }}</span></div>
          <div class="automation-actions" @click.stop>
            <a-button v-if="run.status === 'draft' || run.status === 'interrupted'" size="small" @click="control(run, 'start')">启动</a-button>
            <a-button v-if="run.status === 'running'" size="small" @click="control(run, 'pause')">暂停</a-button>
            <a-button v-if="run.status === 'paused'" size="small" @click="control(run, 'resume')">继续</a-button>
            <a-button v-if="['running','paused'].includes(run.status)" size="small" danger @click="control(run, 'stop')">停止</a-button>
          </div>
        </article>
      </section>
      <section class="panel automation-events">
        <div class="panel-heading">
          <h2>实时事件</h2>
          <div class="automation-event-controls">
            <span>{{ selected ? `任务 #${selected.id}` : '请选择任务' }}</span>
            <a-button v-if="selected?.status === 'running'" size="small" @click="control(selected, 'pause')">暂停投递</a-button>
            <a-button v-if="selected?.status === 'paused'" size="small" type="primary" @click="control(selected, 'resume')">继续投递</a-button>
            <a-button v-if="selected && ['running','paused'].includes(selected.status)" size="small" danger @click="control(selected, 'stop')">停止</a-button>
          </div>
        </div>
        <div v-if="selected?.stopReason" class="automation-blocker" :class="{ neutral: !isErrorStatus(selected.status) }">{{ reasonText(selected.stopReason) }}</div>
        <div v-if="report" class="automation-report-summary">
          <strong>投递结果</strong>：成功 {{ report.run.successCount }} · 失败 {{ report.run.failureCount }}
          <span>浏览器动作：成功 {{ actionSuccessCount }} · 失败 {{ actionFailureCount }}</span>
        </div>
        <div v-if="!events.length" class="library-empty">暂无事件。</div>
        <ol v-else><li v-for="event in events" :key="event.id"><span>#{{ event.sequence }}</span><strong>{{ eventName(event.eventType) }}</strong><time>{{ formatTime(event.createdAt) }}</time><p>{{ eventText(event) }}</p></li></ol>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import { formatTime } from '../../utils/format'
import type { AutomationEvent, AutomationReport, AutomationRun, BrowserProtocolStatus, SetupStatus } from '../../types'

const targetCount = ref(20)
const creating = ref(false)
const runs = ref<AutomationRun[]>([])
const selected = ref<AutomationRun>()
const events = ref<AutomationEvent[]>([])
const report = ref<AutomationReport>()
const setup = ref<SetupStatus>()
const browser = ref<BrowserProtocolStatus>()
let stream: EventSource | undefined
let refreshTimer: ReturnType<typeof setInterval> | undefined

const names: Record<string, string> = { draft: '待启动', validating: '校验中', ready: '已就绪', running: '运行中', paused: '已暂停', stopping: '停止中', interrupted: '已中断', completed: '已完成', failed: '失败', blocked: '被阻止', cancelled: '已取消' }
const eventNames: Record<string, string> = { 'run-created': '任务已创建', 'status-changed': '状态变化', 'status-corrected': '状态已修正', 'runner-awaiting-host': '等待执行器', 'runner-claimed': '执行器已认领', 'job-finished': '岗位处理完成', 'action-claimed': '浏览器动作开始', 'action-finished': '浏览器动作结束' }
const statusName = (status: string) => names[status] || status
const eventName = (event: string) => eventNames[event] || event
const runnerReady = computed(() => setup.value?.checks.some(item => item.key === 'automation-runner' && item.status === 'ready') ?? false)
const actionSuccessCount = computed(() => report.value?.actions.filter(item => item.status === 'succeeded').length ?? 0)
const actionFailureCount = computed(() => report.value?.actions.filter(item => item.status === 'failed').length ?? 0)
const plannedCount = (run: AutomationRun) => Array.isArray(run.configSnapshot.plannedJobs) ? run.configSnapshot.plannedJobs.length : 0
const isErrorStatus = (status: string) => ['failed', 'blocked', 'cancelled'].includes(status)
const reasonText = (reason: string) => ({ 'plan-finished': '计划处理结束', 'user-requested': '用户已停止任务' }[reason] || reason)
const actionNames: Record<string, string> = { open_job: '打开岗位', open_chat: '打开沟通', validate_identity: '校验岗位身份', send_greeting: '发送问候语', send_resume: '发送简历' }
const eventText = (event: AutomationEvent) => {
  if (event.payload.message || event.payload.reason) return event.payload.message || event.payload.reason
  if (event.eventType === 'status-changed') return `${statusName(event.payload.from)} → ${statusName(event.payload.to)}`
  if (event.eventType === 'run-created') return `目标 ${event.payload.target} 个岗位`
  if (event.eventType === 'action-claimed') return `${actionNames[event.payload.actionType] || event.payload.actionType}已开始`
  if (event.eventType === 'action-finished') {
    const label = actionNames[event.payload.actionType] || event.payload.actionType
    return event.payload.status === 'succeeded' ? `${label}成功` : `${label}失败：${event.payload.error || '未通过安全校验'}`
  }
  return JSON.stringify(event.payload)
}

async function load() { const [runList, setupStatus, browserStatus] = await Promise.all([api.automationRuns(), api.setupStatus(), api.browserStatus()]); runs.value = runList.items; setup.value = setupStatus; browser.value = browserStatus }
async function createRun() { creating.value = true; try { const run = await api.createAutomationRun(targetCount.value); await load(); await selectRun(run); const count = plannedCount(run); count ? message.success(`任务已创建，计划处理 ${count} 个岗位`) : message.warning('任务没有可执行岗位，启动时会被阻止；请先采集岗位后重新创建') } catch (error) { message.error((error as Error).message) } finally { creating.value = false } }
async function control(run: AutomationRun, action: 'start' | 'pause' | 'resume' | 'stop') { try { selected.value = await api.controlAutomationRun(run.id, action); await load(); await loadEvents(run.id) } catch (error) { message.error((error as Error).message) } }
async function loadEvents(id: number) { report.value = await api.automationReport(id); events.value = report.value.events; selected.value = report.value.run }
async function selectRun(run: AutomationRun) { selected.value = run; await loadEvents(run.id); stream?.close(); stream = new EventSource(`/v1/automation/runs/${run.id}/events/stream?after=${events.value.at(-1)?.sequence || 0}`); stream.onmessage = () => loadEvents(run.id) }

onMounted(() => { refreshTimer = setInterval(() => { void load(); if (selected.value) void loadEvents(selected.value.id) }, 3000) })
onBeforeUnmount(() => { stream?.close(); if (refreshTimer) clearInterval(refreshTimer) })
useRefresh(load)
</script>
