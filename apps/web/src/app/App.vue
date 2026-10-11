<template>
  <a-config-provider :theme="theme">
    <router-view v-if="route.name === 'login'" />
    <a-layout v-else class="app-shell">
      <aside class="sidebar">
        <div class="brand">
          <span class="brand-mark">J</span>
          <div>
            <strong>Job Search</strong>
            <span>Assistant</span>
            <small class="brand-version">Web {{ appVersion }}</small>
          </div>
        </div>
        <nav aria-label="主要导航">
          <a-button
            v-for="item in visibleNavigation"
            :key="item.name"
            class="nav-item"
            :class="{ active: route.name === item.name }"
            :aria-current="route.name === item.name ? 'page' : undefined"
            @click="router.push(item.path)"
          >
            <span class="nav-icon">{{ item.icon }}</span>{{ item.label }}
          </a-button>
        </nav>
        <div class="sidebar-footer">
          <span class="status-dot" :class="{ online: service.online }"></span>
          <div><strong>{{ service.text }}</strong><span>数据仅保存在这台设备</span></div>
        </div>
      </aside>

      <a-layout-content class="main-content">
        <header class="topbar">
          <div><p class="eyebrow">本地知识库</p><h1>{{ pageTitle }}</h1></div>
          <div class="topbar-account">
            <span v-if="username" class="account-name">{{ username }}</span>
            <a-button :loading="signingOut" @click="confirmSignOut">退出登录</a-button>
          </div>
        </header>
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-config-provider>
</template>

<script setup lang="ts">
import { Modal } from 'ant-design-vue'
import { computed, onMounted, onUnmounted, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../services/api'

const route = useRoute()
const router = useRouter()
const refreshVersion = ref(0)
const service = reactive({ online: false, text: '正在连接本地服务' })
const isAdmin = ref(false)
const username = ref('')
const signingOut = ref(false)
const rawAppVersion = String(import.meta.env.VITE_APP_VERSION || 'dev')
const appVersion = rawAppVersion.startsWith('v') ? rawAppVersion : `v${rawAppVersion}`
let authWatchTimer: number | undefined

provide('refreshVersion', refreshVersion)

const navigation = [
  { name: 'setup', path: '/setup', label: '安装向导', icon: '✓' },
  { name: 'automation', path: '/automation', label: '自动投递', icon: '▶' },
  { name: 'jobs', path: '/jobs', label: '职位快照', icon: '▤' },
  { name: 'profile', path: '/profile', label: '个人档案', icon: '◎' },
  { name: 'projects', path: '/projects', label: '项目库', icon: '◇' },
  { name: 'resumes', path: '/resumes', label: '简历库', icon: '▧' },
  { name: 'rules', path: '/rules', label: '匹配规则', icon: '⌁' },
  { name: 'models', path: '/models', label: '模型配置', icon: '✦' },
]

const adminNavigation = { name: 'admin-users', path: '/admin/users', label: '用户管理', icon: '♙' }
const visibleNavigation = computed(() => isAdmin.value ? [...navigation, adminNavigation] : navigation)

const pageTitle = computed(() => String(route.meta.title || '自动投递'))

onMounted(async () => {
  const redirectIfTokenMissing = () => {
    if (route.name !== 'login' && !localStorage.getItem('jsa_access_token')) {
      router.replace({ name: 'login' })
    }
  }
  redirectIfTokenMissing()
  authWatchTimer = window.setInterval(redirectIfTokenMissing, 500)

  try {
    const me = await api.me()
    isAdmin.value = me.user.isAdmin
    username.value = me.user.username
  } catch {
    // Authentication state must not affect the service-health indicator.
    // The router handles unauthenticated users; keep the shell usable while
    // the auth request is settling (or when an expired token is present).
    isAdmin.value = false
    username.value = ''
  }

  try {
    const health = await api.health()
    service.online = true
    service.text = `本地服务 ${health.version}`
  } catch {
    service.online = false
    service.text = '本地服务连接失败'
  }
})

onUnmounted(() => {
  if (authWatchTimer !== undefined) window.clearInterval(authWatchTimer)
})

async function signOut() {
  signingOut.value = true
  try {
    await api.logout()
  } catch {
    // 登出接口失败也要回到登录页，本地会话以清 token 为准。
  } finally {
    localStorage.removeItem('jsa_access_token')
    signingOut.value = false
    router.replace({ name: 'login' })
  }
}

function confirmSignOut() {
  Modal.confirm({
    title: '确认退出登录？',
    content: '退出后将返回登录页面，需要重新登录才能继续使用。',
    okText: '确认退出',
    okType: 'danger',
    cancelText: '取消',
    onOk: signOut,
  })
}

const theme = {
  token: {
    colorPrimary: '#176b55',
    colorInfo: '#176b55',
    borderRadius: 9,
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
}
</script>
