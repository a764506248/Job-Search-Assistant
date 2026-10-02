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
        <div v-if="browserCheck" class="setup-browser-content">
          <div class="setup-browser-state" :class="`is-${browserCheck.status}`">
            <span class="setup-check-icon">{{ statusIcon(browserCheck.status) }}</span>
            <div><strong>{{ browserCheck.label }}</strong><p>{{ browserCheck.message }}</p></div>
          </div>
          <ol>
            <li><strong>启动 Docker 服务</strong><span>本地 API、数据库与向量模型保持运行。</span></li>
            <li><strong>启动 Kimi 并安装项目扩展</strong><span>当前阶段由 Kimi WebBridge 控制已登录的浏览器。</span></li>
            <li><strong>登录 BOSS 直聘</strong><span>账号会话只留在你的浏览器中。</span></li>
          </ol>
        </div>
      </section>

      <section id="services" class="setup-next-step">
        <div>
          <p class="eyebrow">READY TO RUN</p>
          <h2>{{ canContinue ? '本地准备已完成' : '完成阻塞项后即可开始投递' }}</h2>
          <p>{{ canContinue ? '浏览器环境确认完成后，可以进入自动投递流程。' : '优先处理标记为“需处理”的项目；可选项不会阻止继续配置。' }}</p>
        </div>
        <a-button type="primary" :disabled="!canContinue">开始投递</a-button>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import type { SetupCheckStatus, SetupStatus } from '../../types'

const router = useRouter()
const status = ref<SetupStatus>()
const loading = ref(false)
const error = ref('')

const localChecks = computed(() => status.value?.checks.filter((check) => check.key !== 'browser') || [])
const browserCheck = computed(() => status.value?.checks.find((check) => check.key === 'browser'))
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

useRefresh(load)
</script>
