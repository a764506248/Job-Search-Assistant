<template><div class="view active-view"><LibraryManager kind="projects" eyebrow="PROJECT KNOWLEDGE" form-title="添加项目" name-placeholder="例如：企业知识库问答系统" submit-label="保存项目" list-eyebrow="YOUR PROJECTS" list-title="项目库" :fields="fields" :display="display" /></div></template>
<script setup lang="ts">
import LibraryManager, { type FieldDefinition } from '../../components/library/LibraryManager.vue'
import type { LibraryRecord } from '../../types'
const fields: FieldDefinition[] = [
  { key: 'repositoryUrl', label: 'GitHub 仓库', type: 'url', placeholder: 'https://github.com/...' },
  { key: 'summary', label: '项目说明', type: 'textarea', rows: 4, placeholder: '项目背景、目标和解决的问题' },
  { key: 'role', label: '角色与职责', type: 'textarea', rows: 3, placeholder: '你在项目中的职责和贡献' },
  { key: 'technologies', label: '技术栈', placeholder: 'Python, FastAPI, LangGraph, RAG' },
  { key: 'achievements', label: '项目成果', type: 'textarea', rows: 4, placeholder: '可验证的业务成果、性能提升或交付结果' },
  { key: 'tags', label: '标签', placeholder: 'RAG, Python, FastAPI, 系统设计' },
]
const display = (record: LibraryRecord) => record.data.summary || record.data.repositoryUrl || '尚未填写项目说明'
</script>
