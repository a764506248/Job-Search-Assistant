<template>
  <main class="auth-page">
    <section class="auth-card">
      <p class="eyebrow">JOB SEARCH ASSISTANT</p>
      <h1>申请注册</h1>
      <p class="auth-hint">每个来源 IP 只能申请一个账号。提交后需管理员审核通过，才能登录使用。</p>

      <div v-if="submitted" class="auth-success" role="status">
        <strong>申请已提交</strong>
        <span>账号正在等待管理员审核，通过后即可登录。</span>
        <router-link to="/login">返回登录</router-link>
      </div>

      <form v-else @submit.prevent="submit">
        <label>用户名<input v-model.trim="username" autocomplete="username" required minlength="3" maxlength="80" /></label>
        <label>密码<input v-model="password" type="password" autocomplete="new-password" required minlength="8" /></label>
        <label>确认密码<input v-model="confirmation" type="password" autocomplete="new-password" required minlength="8" /></label>
        <p v-if="error" class="auth-error">{{ error }}</p>
        <button type="submit" :disabled="loading">{{ loading ? '正在提交…' : '提交注册申请' }}</button>
      </form>

      <p v-if="!submitted" class="auth-switch">已有账号？<router-link to="/login">返回登录</router-link></p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../../services/api'

const username = ref('')
const password = ref('')
const confirmation = ref('')
const loading = ref(false)
const submitted = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (password.value !== confirmation.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    const result = await api.register(username.value, password.value)
    if (result.pendingApproval) submitted.value = true
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '注册失败'
  } finally {
    loading.value = false
  }
}
</script>
