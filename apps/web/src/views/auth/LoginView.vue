<template>
  <main class="auth-page">
    <section class="auth-card">
      <p class="eyebrow">JOB SEARCH ASSISTANT</p>
      <h1>{{ needsSetup ? '创建管理员账号' : '登录' }}</h1>
      <p class="auth-hint">
        {{ needsSetup
          ? '这是本机第一次启动，先创建一个管理员账号；之后的账号由管理员在“用户管理”中创建。'
          : '账号数据、简历和投递任务将按用户隔离保存。' }}
      </p>
      <form @submit.prevent="submit">
        <label>用户名<input v-model.trim="username" autocomplete="username" required minlength="3" /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" required minlength="8" /></label>
        <p v-if="error" class="auth-error">{{ error }}</p>
        <button type="submit" :disabled="loading || checking">
          {{ checking ? '正在检查…' : loading ? '处理中…' : needsSetup ? '创建并进入' : '登录' }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../services/api'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const checking = ref(true)
const needsSetup = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    // 首次启动时先创建管理员，再走正常登录流程拿到令牌。
    if (needsSetup.value) await api.register(username.value, password.value)
    await api.login(username.value, password.value)
    await router.replace('/')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '操作失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    needsSetup.value = (await api.bootstrap()).needsSetup
  } catch {
    needsSetup.value = false
  } finally {
    checking.value = false
  }
})
</script>
