<template>
  <main class="auth-page">
    <section class="auth-card">
      <p class="eyebrow">JOB SEARCH ASSISTANT</p>
      <h1>{{ registering ? '创建账号' : '登录' }}</h1>
      <p class="auth-hint">账号数据、简历和投递任务将按用户隔离保存。</p>
      <form @submit.prevent="submit">
        <label>用户名<input v-model.trim="username" autocomplete="username" required minlength="3" /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" required minlength="8" /></label>
        <p v-if="error" class="auth-error">{{ error }}</p>
        <button type="submit" :disabled="loading">{{ loading ? '处理中…' : registering ? '创建并登录' : '登录' }}</button>
      </form>
      <button class="link-button" type="button" @click="registering = !registering">{{ registering ? '已有账号，返回登录' : '申请新账号' }}</button>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../services/api'

const router = useRouter()
const username = ref('')
const password = ref('')
const registering = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    if (registering.value) await api.register(username.value, password.value)
    else await api.login(username.value, password.value)
    await router.replace('/')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '操作失败'
  } finally {
    loading.value = false
  }
}
</script>
