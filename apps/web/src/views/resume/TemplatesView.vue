<template>
  <div class="view active-view"><div class="template-layout">
    <aside class="panel template-picker">
      <div class="panel-heading"><div><p class="eyebrow">RESUME TEMPLATES</p><h2>选择投递版式</h2></div></div>
      <div v-if="loading" class="library-empty">正在读取模板…</div>
      <div v-else class="template-list">
        <article v-for="template in templates" :key="template.id" class="template-option" :class="{ selected: selectedTemplate === template.id }">
          <div class="template-swatch" :style="{ '--template-accent': template.accent }"><span></span><span></span><span></span></div>
          <div><h3>{{ template.name }}</h3><p>{{ template.description }}</p></div>
          <div class="template-buttons"><a-button type="primary" :disabled="selectedTemplate === template.id" @click="selectTemplate(template.id)">{{ selectedTemplate === template.id ? '当前模板' : '选择模板' }}</a-button><a-button :href="`/v1/resume-templates/${template.id}/sample.pdf`" target="_blank">查看 PDF 示例</a-button></div>
        </article>
      </div>
    </aside>
    <section>
      <div class="section-title"><div><p class="eyebrow">LIVE PREVIEW</p><h2>简历示例预览</h2></div><span class="library-count">{{ selectedName }}</span></div>
      <article class="resume-paper"><iframe v-if="selectedTemplate" class="resume-preview-frame" title="简历模板连续预览" :src="`/v1/resume-templates/${selectedTemplate}/sample`" @load="fitFrame" /></article>
    </section>
  </div></div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import type { ResumeTemplate } from '../../types'

const templates = ref<ResumeTemplate[]>([])
const selectedTemplate = ref('')
const loading = ref(false)
const selectedName = computed(() => templates.value.find((item) => item.id === selectedTemplate.value)?.name || '')

async function load() {
  loading.value = true
  try {
    const [templateResult, profileResult] = await Promise.all([api.templates(), api.profile()])
    templates.value = templateResult.items
    selectedTemplate.value = profileResult.data.resumeTemplateId || templateResult.items[0]?.id || ''
  } catch (error) { message.error((error as Error).message) }
  finally { loading.value = false }
}

async function selectTemplate(id: string) {
  try {
    const profile = (await api.profile()).data
    await api.saveProfile({ ...profile, resumeTemplateId: id })
    selectedTemplate.value = id
    message.success('已设为默认投递模板')
  } catch (error) { message.error((error as Error).message) }
}

function fitFrame(event: Event) {
  const frame = event.target as HTMLIFrameElement
  const root = frame.contentDocument?.documentElement
  const body = frame.contentDocument?.body
  const height = Math.max(root?.scrollHeight || 0, root?.offsetHeight || 0, body?.scrollHeight || 0, body?.offsetHeight || 0)
  if (height) frame.style.height = `${height}px`
}

useRefresh(load)
</script>
