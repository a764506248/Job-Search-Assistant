<template>
  <div class="library-layout">
    <section class="panel form-panel">
      <div class="panel-heading"><div><p class="eyebrow">{{ eyebrow }}</p><h2>{{ formTitle }}</h2></div></div>
      <form class="data-form" @submit.prevent="save">
        <label>名称<input v-model.trim="form.name" required :placeholder="namePlaceholder" /></label>
        <label v-for="field in fields" :key="field.key">
          {{ field.label }}
          <textarea v-if="field.type === 'textarea'" v-model="form.data[field.key]" :rows="field.rows || 4" :placeholder="field.placeholder"></textarea>
          <select v-else-if="field.type === 'select'" v-model="form.data[field.key]">
            <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
          <input
            v-else
            v-model="form.data[field.key]"
            :type="field.type || 'text'"
            :required="Boolean(field.required && !(editingId && field.key === 'apiKey'))"
            :autocomplete="field.type === 'password' ? 'new-password' : undefined"
            :placeholder="field.placeholder"
          />
        </label>
        <p v-if="note" class="form-note">{{ note }}</p>
        <div class="form-actions">
          <a-button type="primary" html-type="submit" :loading="saving">{{ editingId ? '保存修改' : submitLabel }}</a-button>
          <a-button v-if="editingId" @click="resetForm">取消编辑</a-button>
        </div>
      </form>
    </section>

    <section>
      <div class="section-title"><div><p class="eyebrow">{{ listEyebrow }}</p><h2>{{ listTitle }}</h2></div><span class="library-count">{{ records.length }} 条记录</span></div>
      <div v-if="loading" class="library-empty">正在读取本地数据…</div>
      <div v-else-if="!records.length" class="library-empty">还没有数据，请使用左侧表单添加第一条记录。</div>
      <div v-else class="record-grid">
        <article v-for="record in records" :key="record.id" class="record-card">
          <div v-if="kind === 'resumes' && record.data.previewImageFile" class="resume-image-preview"><img :src="`/v1/resumes/${record.id}/preview-image`" :alt="`${record.name} 第一页预览`" /></div>
          <div class="record-card-head">
            <div><h3>{{ record.name }}</h3><p>{{ display(record) }}</p></div>
            <div class="record-actions">
              <a-button v-if="kind === 'resumes' && record.data.previewImageFile" size="small" :type="record.data.isDefaultImage ? 'primary' : 'default'" :disabled="Boolean(record.data.isDefaultImage)" @click="setDefaultImage(record)">{{ record.data.isDefaultImage ? '默认投递图片' : '设为默认图片' }}</a-button>
              <a-button v-if="kind === 'models'" size="small" :loading="testingId === record.id" @click="testModel(record)">验证连接</a-button>
              <a-button size="small" @click="edit(record)">编辑</a-button>
              <a-button size="small" danger @click="confirmDelete(record)">删除</a-button>
            </div>
          </div>
          <p v-if="modelStatuses[record.id]" class="model-test-status" :class="modelStatuses[record.id].ok ? 'status-good' : 'status-bad'">{{ modelStatuses[record.id].text }}</p>
          <div v-if="record.data.tags" class="tags"><span v-for="tag in String(record.data.tags).split(',').filter(Boolean)" :key="tag" class="tag">{{ tag.trim() }}</span></div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Modal, message } from 'ant-design-vue'
import { reactive, ref } from 'vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import type { LibraryRecord } from '../../types'

export interface FieldOption { label: string; value: string }
export interface FieldDefinition {
  key: string
  label: string
  type?: 'text' | 'url' | 'password' | 'textarea' | 'select'
  placeholder?: string
  required?: boolean
  rows?: number
  defaultValue?: string
  options?: FieldOption[]
}

const props = defineProps<{
  kind: string
  eyebrow: string
  formTitle: string
  namePlaceholder: string
  submitLabel: string
  listEyebrow: string
  listTitle: string
  fields: FieldDefinition[]
  note?: string
  display: (record: LibraryRecord) => string
}>()

const records = ref<LibraryRecord[]>([])
const loading = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const testingId = ref<number | null>(null)
const modelStatuses = reactive<Record<number, { ok: boolean; text: string }>>({})
const form = reactive<{ name: string; data: Record<string, any> }>({ name: '', data: {} })

function defaults() {
  return Object.fromEntries(props.fields.map((field) => [field.key, field.defaultValue || '']))
}

function resetForm() {
  editingId.value = null
  form.name = ''
  form.data = defaults()
}

async function reload() {
  loading.value = true
  try { records.value = (await api.library(props.kind)).items }
  catch (error) { message.error((error as Error).message) }
  finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    const data = { ...form.data }
    if (props.kind === 'models' && editingId.value && !data.apiKey) delete data.apiKey
    if (editingId.value) await api.updateRecord(props.kind, editingId.value, form.name, data)
    else await api.createRecord(props.kind, form.name, data)
    resetForm()
    await reload()
    message.success('数据已保存')
  } catch (error) { message.error((error as Error).message) }
  finally { saving.value = false }
}

function edit(record: LibraryRecord) {
  editingId.value = record.id
  form.name = record.name
  form.data = { ...defaults(), ...record.data, ...(props.kind === 'models' ? { apiKey: '' } : {}) }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function confirmDelete(record: LibraryRecord) {
  Modal.confirm({
    title: '确定删除这条本地记录吗？',
    content: record.name,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await api.deleteRecord(props.kind, record.id)
      if (editingId.value === record.id) resetForm()
      await reload()
      message.success('记录已删除')
    },
  })
}

async function testModel(record: LibraryRecord) {
  testingId.value = record.id
  modelStatuses[record.id] = { ok: true, text: '正在发送最小测试请求…' }
  try {
    const result = await api.testModel(record.id)
    modelStatuses[record.id] = { ok: true, text: `✓ ${result.message}，耗时 ${result.latencyMs} ms` }
    message.success('模型连接验证成功')
  } catch (error) {
    modelStatuses[record.id] = { ok: false, text: `✗ ${(error as Error).message}` }
    message.error('模型连接验证失败')
  } finally { testingId.value = null }
}

async function setDefaultImage(record: LibraryRecord) {
  try {
    await api.setDefaultResumeImage(record.id)
    await reload()
    message.success('默认投递简历图片已更新')
  } catch (error) { message.error((error as Error).message) }
}

resetForm()
useRefresh(reload)
defineExpose({ reload })
</script>
