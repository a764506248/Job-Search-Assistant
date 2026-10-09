<template>
  <section class="page-stack admin-users-page">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">ADMINISTRATION</p>
        <h2>用户管理</h2>
        <p class="muted">仅管理员可见；可创建、停用、恢复和删除账号。</p>
      </div>
      <a-button type="primary" @click="openCreate">创建用户</a-button>
    </div>

    <a-modal
      v-model:open="showCreate"
      title="创建用户"
      ok-text="创建"
      cancel-text="取消"
      :confirm-loading="loading"
      :ok-button-props="{ disabled: !canSubmit }"
      @ok="createUser"
    >
      <div class="admin-user-form">
        <label><span>用户名</span><a-input v-model:value="newUsername" placeholder="至少 3 个字符" allow-clear /></label>
        <label><span>初始密码</span><a-input-password v-model:value="newPassword" placeholder="至少 8 位" /></label>
        <a-checkbox v-model:checked="newIsAdmin">设为管理员</a-checkbox>
        <p v-if="error" class="auth-error">{{ error }}</p>
      </div>
    </a-modal>

    <p v-if="error && !showCreate" class="auth-error">{{ error }}</p>

    <div class="table-panel">
      <table>
        <thead>
          <tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.isAdmin ? '管理员' : '普通用户' }}</td>
            <td><span class="status-tag" :class="user.isActive ? 'is-active' : 'is-inactive'">{{ user.isActive ? '启用' : '已停用' }}</span></td>
            <td>{{ formatDate(user.createdAt) }}</td>
            <td class="admin-actions">
              <a-button size="small" @click="toggle(user)">{{ user.isActive ? '停用' : '恢复' }}</a-button>
              <a-button size="small" @click="toggleAdmin(user)">{{ user.isAdmin ? '取消管理员' : '设为管理员' }}</a-button>
              <a-button size="small" danger @click="remove(user)">删除</a-button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { api, type AdminUser } from '../../services/api'

const users = ref<AdminUser[]>([])
const loading = ref(false)
const error = ref('')
const showCreate = ref(false)
const newUsername = ref('')
const newPassword = ref('')
const newIsAdmin = ref(false)

const canSubmit = computed(() => newUsername.value.trim().length >= 3 && newPassword.value.length >= 8)

function messageOf(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback
}

function openCreate() {
  error.value = ''
  showCreate.value = true
}

async function load() {
  try {
    users.value = (await api.adminUsers()).items
  } catch (cause) {
    error.value = messageOf(cause, '加载用户失败')
  }
}

async function createUser() {
  if (!canSubmit.value) return
  loading.value = true
  error.value = ''
  try {
    await api.adminCreateUser(newUsername.value.trim(), newPassword.value, newIsAdmin.value)
    newUsername.value = ''
    newPassword.value = ''
    newIsAdmin.value = false
    showCreate.value = false
    await load()
  } catch (cause) {
    error.value = messageOf(cause, '创建失败')
  } finally {
    loading.value = false
  }
}

async function toggle(user: AdminUser) {
  error.value = ''
  try {
    await api.adminUpdateUser(user.id, { isActive: !user.isActive })
    await load()
  } catch (cause) {
    error.value = messageOf(cause, '操作失败')
  }
}

async function toggleAdmin(user: AdminUser) {
  error.value = ''
  try {
    await api.adminUpdateUser(user.id, { isAdmin: !user.isAdmin })
    await load()
  } catch (cause) {
    error.value = messageOf(cause, '操作失败')
  }
}

function remove(user: AdminUser) {
  Modal.confirm({
    title: '删除用户',
    content: `确定删除用户「${user.username}」？该操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      error.value = ''
      try {
        await api.adminDeleteUser(user.id)
        await load()
      } catch (cause) {
        error.value = messageOf(cause, '删除失败')
      }
    },
  })
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(load)
</script>
