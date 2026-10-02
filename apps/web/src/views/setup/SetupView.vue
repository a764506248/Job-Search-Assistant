<template>
  <div class="view active-view setup-view">
    <section class="setup-hero">
      <div>
        <span class="pill">首次使用</span>
        <h2>从安装到开始投递，只检查必要步骤</h2>
        <p>本页读取本地服务的真实状态。完成简历、模型和投递偏好配置后，再确认浏览器环境。</p>
      </div>
      <div class="setup-score" :class="`is-${status?.overall || 'pending'}`">
        <strong>{{ status?.completed || 0 }}/{{ status?.total || 0 }}</strong>
        <span>已就绪</span>
      </div>
    </section>

    <div v-if="error" class="setup-error" role="alert">
      <strong>无法读取安装状态</strong>
      <span>{{ error }}</span>
      <a-button @click="load">重新连接</a-button>
    </div>

    <template v-else>
      <section class="setup-section">
        <div class="setup-section-heading">
          <div><p class="eyebrow">LOCAL CHECKS</p><h2>本机服务与资料</h2></div>
          <a-button :loading="loading" @click="load">刷新状态</a-button>
        </div>
        <div v-if="loading && !status" class="library-empty">正在检查本机环境…</div>
        <div v-else class="setup-check-grid">
          <article v-for="check in localChecks" :key="check.key" class="setup-check-card" :class="`is-${check.status}`">
            <header>
              <span class="setup-check-icon" aria-hidden="true">{{ statusIcon(check.status) }}</span>
              <span class="setup-status-label">{{ statusLabel(check.status) }}</span>
            </header>
            <h3>{{ check.label }}</h3>
            <p>{{ check.message }}</p>
            <a-button v-if="check.actionPath" type="link" @click="go(check.actionPath)">
              {{ check.actionLabel }} →
            </a-button>
          </article>
        </div>
      </section>

      <section id="browser" class="setup-section setup-browser-panel">
        <div class="setup-section-heading">
          <div><p class="eyebrow">BROWSER CHECK</p><h2>浏览器投递环境</h2></div>
          <span class="setup-phase">阶段 1</span>
        </div>
        <div class="setup-browser-content">
          <div class="setup-browser-states">
            <div v-for="check in browserChecks" :key="check.key" class="setup-browser-state" :class="`is-${check.status}`">
              <span class="setup-check-icon">{{ statusIcon(check.status) }}</span>
              <div><strong>{{ check.label }}</strong><p>{{ check.message }}</p></div>
            </div>
          </div>
          <form class="browser-probe-form" @submit.prevent="saveBrowserProbe">
            <p>请在本机和 BOSS 页面核对后确认。状态保存 12 小时，过期后需要重新检查。</p>
            <label><input v-model="probe.webbridgeRunning" type="checkbox" /> WebBridge 正在运行</label>
            <label><input v-model="probe.kimiExtensionConnected" type="checkbox" /> Kimi 浏览器扩展已连接</label>
            <label><input v-model="probe.projectExtensionReady" type="checkbox" /> BOSS 页面已显示简历图片面板</label>
            <label><input v-model="probe.bossLoggedIn" type="checkbox" /> 已登录 BOSS 直聘</label>
            <label class="browser-probe-version">Skill 版本<input v-model.trim="probe.skillVersion" placeholder="例如 5.10.0" /></label>
            <a-button type="primary" html-type="submit" :loading="savingProbe">保存检查结果</a-button>
          </form>
        </div>
      </section>

      <section id="services" class="setup-next-step">
        <div>
          <p class="eyebrow">READY TO RUN</p>
          <h2>{{ canContinue ? '本地准备已完成' : '完成阻塞项后即可开始投递' }}</h2>
          <p>{{ canContinue ? '可以先运行无副作用测试；当前版本仍通过 Skill 启动真实投递。' : '优先处理标记为“需处理”的项目；安全测试不会打开 BOSS 页面或执行点击。' }}</p>
        </div>
        <a-button type="primary" :loading="testingSetup" @click="runSafeTest">运行安全测试</a-button>
      </section>
      <div v-if="testResult" class="setup-test-result" :class="testResult.ok ? 'is-ready' : 'is-blocked'">
        <strong>{{ testResult.ok ? '安全测试通过' : '安全测试未通过' }}</strong>
        <p>{{ testResult.message }}</p>
        <span>浏览器动作：{{ testResult.browserActionsExecuted ? '已执行' : '未执行' }} · 每日目标：{{ testResult.dailyTarget }} · 关键词：{{ testResult.plannedKeywords.join('、') || '未配置' }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import type { BrowserProbe, SetupCheckStatus, SetupStatus, SetupTestRunResult } from '../../types'

const router = useRouter()
const status = ref<SetupStatus>()
const loading = ref(false)
const error = ref('')
const savingProbe = ref(false)
const testingSetup = ref(false)
const testResult = ref<SetupTestRunResult>()
const browserKeys = new Set(['kimi-webbridge', 'project-extension', 'boss-login', 'skill-version'])
const probe = ref<BrowserProbe>({
  webbridgeRunning: false,
  kimiExtensionConnected: false,
  projectExtensionReady: false,
  bossLoggedIn: false,
  skillVersion: '5.10.0',
  source: 'manual',
})

const localChecks = computed(() => status.value?.checks.filter((check) => !browserKeys.has(check.key)) || [])
const browserChecks = computed(() => status.value?.checks.filter((check) => browserKeys.has(check.key)) || [])
const canContinue = computed(() => Boolean(status.value) && !status.value!.checks.some((check) => check.blocking && check.status !== 'ready'))

const labels: Record<SetupCheckStatus, string> = {
  ready: '已就绪',
  pending: '待确认',
  warning: '需验证',
  blocked: '需处理',
}

function statusLabel(value: SetupCheckStatus) {
  return labels[value]
}

function statusIcon(value: SetupCheckStatus) {
  return value === 'ready' ? '✓' : value === 'blocked' ? '!' : '…'
}

function go(path: string) {
  router.push(path)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = await api.setupStatus()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    loading.value = false
  }
}

async function saveBrowserProbe() {
  savingProbe.value = true
  try {
    await api.saveBrowserProbe(probe.value)
    await load()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    savingProbe.value = false
  }
}

async function runSafeTest() {
  testingSetup.value = true
  try {
    testResult.value = await api.runSetupTest()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    testingSetup.value = false
  }
}

useRefresh(load)
</script>
