<template><div class="view active-view"><LibraryManager kind="models" eyebrow="MODEL PROVIDERS" form-title="添加模型配置" name-placeholder="例如：主分析模型" submit-label="保存模型配置" list-eyebrow="CONFIGURED MODELS" list-title="模型配置" :fields="fields" :display="display" note="API Key 仅保存到本机 SQLite，读取列表时不会返回明文；编辑时留空表示保留原 Key。" /></div></template>
<script setup lang="ts">
import LibraryManager, { type FieldDefinition } from '../../components/library/LibraryManager.vue'
import type { LibraryRecord } from '../../types'
const fields: FieldDefinition[] = [
  { key: 'usageRole', label: '调用角色', type: 'select', defaultValue: 'available', options: [
    { value: 'primary', label: '选中模型（主模型）' },
    { value: 'fallback', label: '兜底模型' },
    { value: 'available', label: '普通备用模型' },
  ] },
  { key: 'provider', label: '服务商', type: 'select', defaultValue: 'OpenAI', options: [
    { value: 'OpenAI', label: 'OpenAI' }, { value: 'OpenAI Compatible', label: 'OpenAI Compatible' }, { value: 'Anthropic', label: 'Anthropic' }, { value: '其他', label: '其他' },
  ] },
  { key: 'modelId', label: '模型 ID', required: true, placeholder: '例如：gpt-5-mini' },
  { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'sk-...' },
  { key: 'baseUrl', label: 'API Base URL', type: 'url', required: true, placeholder: 'https://api.openai.com/v1' },
]
const roleNames: Record<string, string> = { primary: '主模型', fallback: '兜底模型', available: '普通备用' }
const display = (record: LibraryRecord) => `${roleNames[record.data.usageRole] || '普通备用'} · ${record.data.provider || '未指定服务商'} · ${record.data.modelId || '未填写模型 ID'} · ${record.data.apiKeyConfigured ? `Key ${record.data.apiKeyHint || '已配置'}` : 'Key 未配置'}`
</script>
