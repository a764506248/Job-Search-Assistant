<template><div class="view active-view"><LibraryManager kind="rules" eyebrow="MATCHING POLICY" form-title="添加匹配规则" name-placeholder="例如：名校学历偏好" submit-label="保存规则" list-eyebrow="ACTIVE RULES" list-title="匹配规则" :fields="fields" :display="display" /></div></template>
<script setup lang="ts">
import LibraryManager, { type FieldDefinition } from '../../components/library/LibraryManager.vue'
import { actionLabel } from '../../utils/format'
import type { LibraryRecord } from '../../types'
const fields: FieldDefinition[] = [
  { key: 'pattern', label: '匹配关键词（按原文查找，逗号分隔）', placeholder: '例如：985, 211, 第一学历；新投递方向请在个人档案的目标岗位中添加' },
  { key: 'action', label: '命中后动作', type: 'select', defaultValue: 'notify', options: [
    { value: 'notify', label: '仅提醒' }, { value: 'reduce_score', label: '降低匹配分' }, { value: 'use_default_materials', label: '使用默认材料继续投递' }, { value: 'block_delivery', label: '禁止投递' },
  ] },
]
const display = (record: LibraryRecord) => `${record.data.pattern || '未填写条件'} · ${actionLabel(record.data.action)}`
</script>
