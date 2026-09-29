<template>
  <div class="view active-view">
    <section class="panel resume-import-panel">
      <div class="panel-heading"><div><p class="eyebrow">RESUME IMPORT</p><h2>导入现有简历</h2></div></div>
      <form class="resume-import-form" @submit.prevent="importResume">
        <label class="file-drop-zone"><span>选择 PDF、DOCX、TXT 或 Markdown 简历</span><small>文件只在本机解析，最大 10 MB</small><input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.md,.markdown" required @change="selectFile" /></label>
        <label class="resume-model-select">
          <span>简历结构化识别模型</span>
          <select v-model="selectedModelId" :disabled="modelsLoading || !models.length">
            <option v-if="!models.length" value="">未配置模型，将使用本地解析</option>
            <option v-for="model in models" :key="model.id" :value="String(model.id)">{{ model.name }} · {{ roleName(model) }} · {{ model.data.modelId }}</option>
          </select>
          <small v-if="models.length">AI 会一次提取完整档案、优势、技术栈、工作/教育经历和多个独立项目；主模型失败时自动调用兜底模型。</small>
          <small v-else>请先到“模型配置”添加并验证模型；本次仍可使用本地规则导入。</small>
        </label>
        <a-button type="primary" html-type="submit" :loading="importing">{{ importing ? '正在识别并入库…' : models.length ? 'AI 识别并直接入库' : '本地解析并直接入库' }}</a-button>
      </form>
      <div v-if="importMessage" class="import-result"><strong>{{ importMessage.title }}</strong><br />{{ importMessage.detail }}</div>
    </section>
    <LibraryManager ref="manager" kind="resumes" eyebrow="RESUME LIBRARY" form-title="添加简历资料" name-placeholder="例如：默认中文简历" submit-label="保存简历资料" list-eyebrow="RESUME SETS" list-title="简历库" :fields="fields" :display="display" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../../services/api'
import LibraryManager, { type FieldDefinition } from '../../components/library/LibraryManager.vue'
import type { LibraryRecord } from '../../types'

const fields: FieldDefinition[] = [
  { key: 'format', label: '格式', type: 'select', defaultValue: 'PDF', options: [{ value: 'PDF', label: 'PDF' }, { value: 'DOCX', label: 'DOCX' }, { value: 'Markdown', label: 'Markdown' }] },
  { key: 'notes', label: '用途与备注', type: 'textarea', rows: 5, placeholder: '这份简历适合哪些岗位' },
]
const display = (record: LibraryRecord) => `${record.data.format || '未指定格式'} · ${record.data.notes || '暂无备注'}`
const manager = ref<InstanceType<typeof LibraryManager> | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const importing = ref(false)
const importMessage = ref<{ title: string; detail: string } | null>(null)
const models = ref<LibraryRecord[]>([])
const modelsLoading = ref(false)
const selectedModelId = ref('')

async function loadModels() {
  modelsLoading.value = true
  try {
    models.value = (await api.library('models')).items
    if (!models.value.some((item) => String(item.id) === selectedModelId.value)) {
      const primary = models.value.find((item) => item.data.usageRole === 'primary') || models.value[0]
      selectedModelId.value = primary ? String(primary.id) : ''
    }
  } catch (error) { message.error(`模型配置读取失败：${(error as Error).message}`) }
  finally { modelsLoading.value = false }
}

function roleName(model: LibraryRecord) {
  return ({ primary: '主模型', fallback: '兜底模型', available: '普通备用' } as Record<string, string>)[model.data.usageRole] || '普通备用'
}

function selectFile(event: Event) { selectedFile.value = (event.target as HTMLInputElement).files?.[0] || null }
async function importResume() {
  if (!selectedFile.value) return
  importing.value = true
  importMessage.value = null
  try {
    const modelRecordId = selectedModelId.value ? Number(selectedModelId.value) : undefined
    const result = await api.importResume(selectedFile.value, modelRecordId)
    const model = result.aiModelName ? `${result.aiModelName}（${result.aiModelId || '未知模型 ID'}）` : '已配置模型'
    const switched = result.aiAttemptErrors?.length ? `主模型失败后已自动切换兜底模型（${result.aiAttemptErrors.join('；')}）。` : ''
    const ai = result.aiExtractionUsed ? `${model} 已完成${result.aiProfileExtracted ? '完整简历结构化识别并' : ''}拆分 ${result.aiProjectCount} 个项目写入项目库。${switched}` : `AI 结构化提取未执行，已回退本地解析：${result.aiExtractionError || '模型不可用'}。`
    const index = result.indexRebuilt ? `已重建 ${result.indexedChunks} 个向量分片。` : `资料已入库，向量索引未重建：${result.indexError || 'Embedding 服务不可用'}。`
    importMessage.value = { title: `${result.filename} 导入成功`, detail: `个人档案更新 ${result.profileFields.length} 个字段，新增 ${result.projectIds.length} 条项目、1 条简历资料，提取 ${result.extractedCharacters} 个字符。${ai}${index}` }
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await manager.value?.reload()
    message.success('简历已解析并分别写入本地资料库')
  } catch (error) { importMessage.value = { title: '导入失败', detail: (error as Error).message } }
  finally { importing.value = false }
}

onMounted(loadModels)
</script>
