<template>
  <div class="view active-view setup-view">
    <section class="setup-hero">
      <div>
        <span class="pill">首次使用</span>
        <h2>从安装到开始投递，只检查必要步骤</h2>
        <p>启动 Docker 本地服务、配对统一 Chrome 扩展并导入简历后，即可在后台完成职位收集、企业确认和投递。</p>
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
          <div><p class="eyebrow">BROWSER CHECK</p><h2>统一 Chrome 扩展</h2></div>
          <span class="setup-phase">默认链路</span>
        </div>
        <div class="setup-browser-content">
          <div class="browser-pairing-card">
            <span class="setup-phase">搜索 · 收集 · 投递</span>
            <h3>连接浏览器扩展</h3>
            <p v-if="browserProtocol?.connected" class="browser-pairing-ready">
              已连接扩展 {{ browserProtocol.extensionVersion || '' }} · 协议 {{ browserProtocol.protocolVersion }}
            </p>
            <template v-else>
              <p>扩展负责在已登录的 BOSS 页面搜索、收集职位和执行确认后的投递。点击生成一次性配对码，并在扩展弹窗中输入；配对码 10 分钟后失效。</p>
              <strong v-if="pairing" class="browser-pairing-code">{{ pairing.code }}</strong>
            </template>
            <div class="browser-pairing-actions">
              <a-button v-if="!browserProtocol?.connected" type="primary" :loading="pairingLoading" @click="createPairing">生成配对码</a-button>
              <a-button :loading="browserTesting" @click="testUnifiedExtension">测试连接</a-button>
            </div>
            <p v-if="browserMessage" class="browser-pairing-message">{{ browserMessage }}</p>
          </div>
          <div class="setup-browser-states">
            <div v-for="check in browserChecks" :key="check.key" class="setup-browser-state" :class="`is-${check.status}`">
              <span class="setup-check-icon">{{ statusIcon(check.status) }}</span>
              <div><strong>{{ check.label }}</strong><p>{{ check.message }}</p></div>
            </div>
          </div>
          <form class="browser-probe-form" @submit.prevent="saveBrowserProbe">
            <p>扩展连接状态会自动检测；请在 BOSS 页面核对以下两项。手工确认保存 12 小时，过期后需要重新检查。</p>
            <label><input v-model="probe.projectExtensionReady" type="checkbox" /> BOSS 页面已加载统一扩展</label>
            <label><input v-model="probe.bossLoggedIn" type="checkbox" /> 已登录 BOSS 直聘</label>
            <a-button type="primary" html-type="submit" :loading="savingProbe">保存检查结果</a-button>
          </form>
        </div>
      </section>

      <section id="services" class="setup-next-step">
        <div>
          <p class="eyebrow">READY TO RUN</p>
          <h2>{{ canContinue ? '本地准备已完成' : '完成阻塞项后即可开始投递' }}</h2>
          <p>{{ canContinue ? '可以先运行无副作用测试，再到“自动投递”由扩展收集职位、确认企业并启动任务。' : '优先处理标记为“需处理”的项目；安全测试不会打开 BOSS 页面或执行点击。' }}</p>
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
import type { BrowserPairing, BrowserProbe, BrowserProtocolStatus, SetupCheckStatus, SetupStatus, SetupTestRunResult } from '../../types'

const router = useRouter()
const status = ref<SetupStatus>()
const loading = ref(false)
const error = ref('')
const savingProbe = ref(false)
const testingSetup = ref(false)
const testResult = ref<SetupTestRunResult>()
const browserProtocol = ref<BrowserProtocolStatus>()
const pairing = ref<BrowserPairing>()
const pairingLoading = ref(false)
const browserTesting = ref(false)
const browserMessage = ref('')
const browserKeys = new Set(['kimi-webbridge', 'project-extension', 'boss-login', 'skill-version'])
const probe = ref<BrowserProbe>({
  webbridgeRunning: false,
  kimiExtensionConnected: false,
  projectExtensionReady: false,
  bossLoggedIn: false,
  skillVersion: '',
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
    browserProtocol.value = await api.browserStatus()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    loading.value = false
  }
}

async function createPairing() {
  pairingLoading.value = true
  browserMessage.value = ''
  try {
    pairing.value = await api.createBrowserPairing()
  } catch (reason) {
    browserMessage.value = (reason as Error).message
  } finally {
    pairingLoading.value = false
  }
}

async function testUnifiedExtension() {
  browserTesting.value = true
  browserMessage.value = ''
  try {
    const result = await api.testBrowserConnection()
    browserMessage.value = result.status === 'success' ? '扩展响应正常，安全测试未执行页面点击。' : `扩展返回：${result.status}`
    await load()
  } catch (reason) {
    browserMessage.value = (reason as Error).message
  } finally {
    browserTesting.value = false
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
