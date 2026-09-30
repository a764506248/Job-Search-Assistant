<template>
  <div id="knowledge-view" class="view active-view">
    <div class="settings-grid">
      <section class="panel form-panel"><div class="panel-heading"><div><p class="eyebrow">LOCAL RAG</p><h2>本地向量索引</h2></div></div>
        <div class="knowledge-status">
          <div><span>Embedding 服务</span><strong :class="status?.embeddingAvailable ? 'status-good' : 'status-bad'">{{ status ? (status.embeddingAvailable ? '已连接' : '未启动') : '检查中' }}</strong></div>
          <div><span>向量模型</span><strong>{{ status?.model || status?.embeddingService?.model || 'jinaai/jina-embeddings-v2-base-zh' }}</strong></div>
          <div><span>资料来源</span><strong>{{ status?.sources ?? '—' }}</strong></div>
          <div><span>知识实体</span><strong>{{ status?.chunks ?? '—' }}</strong></div>
        </div>
        <div class="knowledge-actions"><span class="status-good">项目库与个人档案变更后自动同步</span><small>{{ status?.indexedAt ? `最后同步：${formatTime(status.indexedAt)}` : '等待结构化资料入库' }}</small></div>
      </section>
      <aside class="panel guidance"><span class="guidance-mark">⌂</span><h3>实体关联，不切简历原文</h3><p>项目知识只来自项目库，并通过项目 ID 与向量记录关联；个人优势、技术栈、工作和教育经历按结构化模块索引。原文、标签与向量都保存在本机 SQLite 中。</p></aside>
    </div>

    <section class="panel vector-data-panel">
      <div class="panel-heading"><div><p class="eyebrow">INDEXED DATA</p><h2>已索引的知识实体</h2></div><div class="panel-heading-actions"><span>{{ filteredChunks.length }} / {{ chunks.length }} 个实体</span><a-button @click="load">刷新数据</a-button></div></div>
      <p class="panel-description">每条向量对应一个结构化实体，并通过实体 ID 关联个人档案或项目库，不再按字符长度切分整份简历。</p>
      <div class="knowledge-filter"><label><span>标签检索</span><input v-model.trim="tagQuery" type="search" placeholder="输入 Python、RAG、Agent 等标签" /></label><div><button v-for="tag in availableTags" :key="tag" type="button" :class="['tag', { active: tagQuery === tag }]" @click="tagQuery = tagQuery === tag ? '' : tag">{{ tag }}</button><button v-if="tagQuery" type="button" class="clear-filter" @click="tagQuery = ''">清除筛选</button></div></div>
      <a-modal v-model:open="detailOpen" width="900px" wrap-class-name="knowledge-detail-modal" :footer="null" centered destroy-on-close @after-close="closeDetail">
        <template #title><div v-if="selectedChunk" class="knowledge-modal-title"><span class="tag">{{ knowledgeTypeLabel(selectedChunk.knowledgeType) }}</span><div><strong>{{ selectedChunk.sourceName }}</strong><small>实体 ID {{ selectedChunk.entityId }} · {{ selectedChunk.dimensions }} 维</small></div></div></template>
        <div v-if="selectedChunk" class="knowledge-detail-modal-body">
          <div v-if="visibleTags(selectedChunk).length" class="knowledge-detail-tags"><span v-for="tag in visibleTags(selectedChunk)" :key="tag" class="tag">{{ tag }}</span></div>
          <section><h3>结构化内容</h3><pre>{{ selectedChunk.content }}</pre></section>
          <section><h3>向量信息</h3><dl><div><dt>实体 ID</dt><dd>{{ selectedChunk.entityId }}</dd></div><div><dt>模型</dt><dd>{{ selectedChunk.model }}</dd></div><div><dt>维度</dt><dd>{{ selectedChunk.dimensions }}</dd></div><div><dt>向量预览</dt><dd>[{{ vectorPreview(selectedChunk) }}]</dd></div><div><dt>内容哈希</dt><dd>{{ selectedChunk.contentHash }}</dd></div><div><dt>索引时间</dt><dd>{{ formatTime(selectedChunk.indexedAt) }}</dd></div></dl></section>
        </div>
      </a-modal>
      <div v-if="chunksLoading" class="library-empty">正在读取本地向量数据…</div>
      <div v-else-if="!filteredChunks.length" class="library-empty">{{ chunks.length ? '没有匹配该标签的知识实体。' : '还没有结构化知识，请先完善个人档案或项目库。' }}</div>
      <div v-else class="vector-record-list">
        <article v-for="item in filteredChunks" :key="item.id" class="vector-record" tabindex="0" @click="openDetail(item)" @keydown.enter="openDetail(item)">
          <header class="vector-record-head">
            <div class="vector-record-title"><span class="tag">{{ knowledgeTypeLabel(item.knowledgeType) }}</span><strong :title="item.sourceName">{{ item.sourceName }}</strong></div>
            <div class="vector-record-meta"><span class="vector-chip">ID {{ item.entityId }}</span><span class="vector-chip">{{ item.dimensions }} 维</span></div>
          </header>
          <div v-if="visibleTags(item).length" class="vector-record-tags"><span class="vector-record-tags-label">业务标签</span><div><span v-for="tag in visibleTags(item)" :key="tag" class="tag">{{ tag }}</span></div></div>
          <div class="vector-record-content">{{ item.content }}</div>
          <footer><span>点击查看详情</span><a-button size="small" danger @click.stop="confirmDelete(item)">删除</a-button></footer>
        </article>
      </div>
    </section>

    <section class="panel search-test-panel">
      <div class="panel-heading"><div><p class="eyebrow">RETRIEVAL TEST</p><h2>语义检索测试</h2></div></div>
      <form class="rag-search-form" @submit.prevent="search"><input v-model.trim="query" required placeholder="例如：需要 Python、FastAPI 和 RAG 经验的岗位" /><a-button type="primary" html-type="submit" :loading="searching">检索项目与简历</a-button></form>
      <div class="rag-results">
        <div v-if="!searching && !results.length" class="library-empty">输入岗位需求，查看知识库命中的真实资料。</div>
        <article v-for="item in results" :key="`${item.sourceId}-${item.chunkIndex}`" class="rag-result"><div><span class="tag">{{ sourceTypeLabel(item.sourceType) }}</span><strong>{{ item.sourceName }}</strong></div><span class="rag-score">综合 {{ percent(item.score) }} · 向量 {{ percent(item.vectorScore) }} · 关键词 {{ percent(item.keywordScore) }}</span><p>{{ item.content }}</p></article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import { formatTime, sourceTypeLabel } from '../../utils/format'
import type { RagChunk, RagSearchResult, RagStatus } from '../../types'

const status = ref<RagStatus | null>(null)
const chunks = ref<RagChunk[]>([])
const results = ref<RagSearchResult[]>([])
const query = ref('')
const searching = ref(false)
const chunksLoading = ref(false)
const tagQuery = ref('')
const selectedChunk = ref<RagChunk | null>(null)
const detailOpen = ref(false)
const percent = (value: number) => `${(value * 100).toFixed(1)}%`
const vectorPreview = (item: RagChunk) => `${item.embedding.slice(0, 8).map((value) => value.toFixed(4)).join(', ')}${item.dimensions > 8 ? ', …' : ''}`
const knowledgeTypeLabel = (value: string) => ({ strengths: '个人优势', 'tech-stack': '技术栈', project: '项目经历', 'work-experience': '工作经历', education: '教育经历' } as Record<string, string>)[value] || sourceTypeLabel(value)
const visibleTags = (item: RagChunk) => [...new Set(item.tags)].filter((tag) => tag !== knowledgeTypeLabel(item.knowledgeType))
const availableTags = computed(() => [...new Set(chunks.value.flatMap(visibleTags))].sort((left, right) => left.localeCompare(right, 'zh-CN')).slice(0, 30))
const filteredChunks = computed(() => {
  const query = tagQuery.value.toLowerCase()
  if (!query) return chunks.value
  return chunks.value.filter((item) => visibleTags(item).some((tag) => tag.toLowerCase().includes(query)))
})

async function loadStatus() { status.value = await api.ragStatus() }
async function loadChunks() { chunksLoading.value = true; try { chunks.value = (await api.ragChunks()).items } catch (error) { message.error((error as Error).message) } finally { chunksLoading.value = false } }
async function load() { try { await Promise.all([loadStatus(), loadChunks()]) } catch (error) { message.error((error as Error).message) } }
async function search() { if (!query.value) return; searching.value = true; try { results.value = (await api.searchRag(query.value)).items } catch (error) { message.error((error as Error).message) } finally { searching.value = false } }
function openDetail(item: RagChunk) { selectedChunk.value = item; detailOpen.value = true }
function closeDetail() { selectedChunk.value = null }
function confirmDelete(item: RagChunk) {
  Modal.confirm({ title: `删除知识实体“${item.sourceName}”？`, content: '只删除当前向量记录，不删除项目库或个人档案源数据。以后重建索引时可能重新生成。', okType: 'danger', async onOk() { await api.deleteRagChunk(item.id); if (selectedChunk.value?.id === item.id) { detailOpen.value = false; selectedChunk.value = null } await load(); message.success('知识实体已从当前索引删除') } })
}
useRefresh(load)
</script>
