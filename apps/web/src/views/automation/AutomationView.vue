<template>
  <div class="view active-view automation-view">
    <section class="automation-command panel">
      <div><p class="eyebrow">AUTOMATION CONTROL</p><h2>自动投递任务</h2><p>任务先校验安装状态；当前执行器未认领前不会操作浏览器。</p></div>
      <label>每日目标<input v-model.number="targetCount" type="number" min="1" max="500" /></label>
      <a-button type="primary" :loading="creating" @click="createRun">创建任务</a-button>
    </section>
    <div class="automation-layout">
      <section class="panel automation-runs">
        <div class="panel-heading"><h2>任务记录</h2><a-button @click="load">刷新</a-button></div>
        <div v-if="!runs.length" class="library-empty">还没有自动投递任务。</div>
        <article v-for="run in runs" :key="run.id" :class="{ selected: selected?.id === run.id }" @click="selectRun(run)">
          <div><strong>#{{ run.id }} · {{ statusName(run.status) }}</strong><span>目标 {{ run.targetCount }} · 成功 {{ run.successCount }} · 失败 {{ run.failureCount }}</span><span v-if="run.runnerId">执行器 {{ run.runnerId }} · 心跳 {{ run.heartbeatAt ? formatTime(run.heartbeatAt) : '等待中' }}</span></div>
          <div class="automation-actions" @click.stop>
            <a-button v-if="run.status === 'draft' || run.status === 'interrupted'" size="small" @click="control(run, 'start')">启动</a-button>
            <a-button v-if="run.status === 'running'" size="small" @click="control(run, 'pause')">暂停</a-button>
            <a-button v-if="run.status === 'paused'" size="small" @click="control(run, 'resume')">继续</a-button>
            <a-button v-if="['running','paused'].includes(run.status)" size="small" danger @click="control(run, 'stop')">停止</a-button>
          </div>
        </article>
      </section>
      <section class="panel automation-events">
        <div class="panel-heading"><h2>实时事件</h2><span>{{ selected ? `任务 #${selected.id}` : '请选择任务' }}</span></div>
        <div v-if="selected?.stopReason" class="automation-blocker">{{ selected.stopReason }}</div>
        <div v-if="report" class="automation-report-summary">动作 {{ report.actions.length }} · 成功 {{ report.actions.filter(item => item.status === 'succeeded').length }} · 失败 {{ report.actions.filter(item => item.status === 'failed').length }}</div>
        <div v-if="!events.length" class="library-empty">暂无事件。</div>
        <ol v-else><li v-for="event in events" :key="event.id"><span>#{{ event.sequence }}</span><strong>{{ event.eventType }}</strong><time>{{ formatTime(event.createdAt) }}</time><p>{{ event.payload.message || event.payload.reason || JSON.stringify(event.payload) }}</p></li></ol>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import { formatTime } from '../../utils/format'
import type { AutomationEvent, AutomationReport, AutomationRun } from '../../types'

const targetCount = ref(20)
const creating = ref(false)
const runs = ref<AutomationRun[]>([])
const selected = ref<AutomationRun>()
const events = ref<AutomationEvent[]>([])
const report = ref<AutomationReport>()
let stream: EventSource | undefined

const names: Record<string, string> = { draft: '待启动', validating: '校验中', ready: '已就绪', running: '运行中', paused: '已暂停', stopping: '停止中', interrupted: '已中断', completed: '已完成', failed: '失败', blocked: '被阻止', cancelled: '已取消' }
const statusName = (status: string) => names[status] || status

async function load() { runs.value = (await api.automationRuns()).items }
async function createRun() { creating.value = true; try { const run = await api.createAutomationRun(targetCount.value); await load(); await selectRun(run) } catch (error) { message.error((error as Error).message) } finally { creating.value = false } }
async function control(run: AutomationRun, action: 'start' | 'pause' | 'resume' | 'stop') { try { selected.value = await api.controlAutomationRun(run.id, action); await load(); await loadEvents(run.id) } catch (error) { message.error((error as Error).message) } }
async function loadEvents(id: number) { report.value = await api.automationReport(id); events.value = report.value.events }
async function selectRun(run: AutomationRun) { selected.value = run; await loadEvents(run.id); stream?.close(); stream = new EventSource(`/v1/automation/runs/${run.id}/events/stream?after=${events.value.at(-1)?.sequence || 0}`); stream.onmessage = () => loadEvents(run.id) }

onBeforeUnmount(() => stream?.close())
useRefresh(load)
</script>
