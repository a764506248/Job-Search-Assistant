<template>
  <section class="page-stack admin-users-page">
    <div class="panel-heading"><div><p class="eyebrow">ADMINISTRATION</p><h2>用户管理</h2><p class="muted">仅管理员可见；可创建、停用、恢复和删除账号。</p></div><button class="primary-button" @click="openCreate">创建用户</button></div>
    <a-modal v-model:open="showCreate" title="创建用户" ok-text="创建" cancel-text="取消" :confirm-loading="loading" @ok="createUser">
      <form class="admin-user-form" @submit.prevent="createUser">
        <label>用户名<input v-model.trim="newUsername" placeholder="至少 3 个字符" minlength="3" required /></label>
        <label>初始密码<input v-model="newPassword" type="password" placeholder="至少 8 位" minlength="8" required /></label>
        <label class="admin-checkbox"><input v-model="newIsAdmin" type="checkbox" /> 设为管理员</label>
        <p v-if="error" class="auth-error">{{ error }}</p>
      </form>
    </a-modal>
    <p v-if="error" class="auth-error">{{ error }}</p>
    <div class="table-panel"><table><thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="user in users" :key="user.id"><td>{{ user.id }}</td><td>{{ user.username }}</td><td>{{ user.isAdmin ? '管理员' : '普通用户' }}</td><td>{{ user.isActive ? '启用' : '已停用' }}</td><td>{{ formatDate(user.createdAt) }}</td><td class="admin-actions"><button @click="toggle(user)">{{ user.isActive ? '停用' : '恢复' }}</button><button @click="toggleAdmin(user)">{{ user.isAdmin ? '取消管理员' : '设为管理员' }}</button><button class="danger-button" @click="remove(user)">删除</button></td></tr></tbody></table></div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type AdminUser } from '../../services/api'
const users = ref<AdminUser[]>([]); const loading = ref(false); const error = ref(''); const showCreate = ref(false); const newUsername = ref(''); const newPassword = ref(''); const newIsAdmin = ref(false)
function openCreate() { error.value = ''; showCreate.value = true }
async function load() { users.value = (await api.adminUsers()).items }
async function createUser() { if (!newUsername.value || !newPassword.value) return; loading.value = true; error.value = ''; try { await api.adminCreateUser(newUsername.value, newPassword.value, newIsAdmin.value); newUsername.value = ''; newPassword.value = ''; newIsAdmin.value = false; showCreate.value = false; await load() } catch (e) { error.value = e instanceof Error ? e.message : '创建失败' } finally { loading.value = false } }
async function toggle(user: AdminUser) { await api.adminUpdateUser(user.id, { isActive: !user.isActive }); await load() }
async function toggleAdmin(user: AdminUser) { await api.adminUpdateUser(user.id, { isAdmin: !user.isAdmin }); await load() }
async function remove(user: AdminUser) { if (window.confirm(`确定删除用户 ${user.username}？`)) { await api.adminDeleteUser(user.id); await load() } }
function formatDate(value: string) { return new Date(value).toLocaleString('zh-CN') }
onMounted(load)
</script>
