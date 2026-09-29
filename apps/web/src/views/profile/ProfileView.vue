<template>
  <div class="view active-view"><div class="settings-grid">
    <section class="panel form-panel"><div class="panel-heading"><div><p class="eyebrow">PROFILE</p><h2>个人档案</h2></div></div>
      <form class="data-form" @submit.prevent="save">
        <label>姓名或称呼<input v-model="profile.displayName" placeholder="例如：小林" /></label>
        <label>目标岗位<input v-model="profile.targetRoles" placeholder="例如：AI应用开发、Python后端" /></label>
        <div class="form-row"><label>工作年限<input v-model="profile.yearsExperience" type="number" min="0" placeholder="3" /></label><label>期望城市<input v-model="profile.cities" placeholder="上海、杭州、远程" /></label></div>
        <div class="form-row"><label>手机号<input v-model="profile.phone" placeholder="用于简历联系方式" /></label><label>邮箱<input v-model="profile.email" type="email" placeholder="name@example.com" /></label></div>
        <label>个人优势<textarea v-model="profile.summary" rows="5" placeholder="概括你的核心能力、业务优势和可验证成果"></textarea></label>
        <label>技术栈<textarea v-model="profile.techStack" rows="3" placeholder="例如：Python、FastAPI、LangGraph、RAG、PostgreSQL"></textarea></label>
        <label>工作经历<textarea v-model="profile.workExperience" rows="6" placeholder="按公司、岗位、时间和主要职责填写"></textarea></label>
        <label>教育经历<textarea v-model="profile.education" rows="4" placeholder="学校、专业、学历和时间"></textarea></label>
        <label>默认问候语<textarea v-model="profile.defaultGreeting" rows="3" placeholder="低匹配岗位使用的默认问候语"></textarea></label>
        <a-button type="primary" html-type="submit" :loading="saving">保存个人档案</a-button>
      </form>
    </section>
    <aside class="panel guidance"><span class="guidance-mark">✓</span><h3>资料使用原则</h3><p>这些内容只保存在本机。生成简历时只会使用你确认过的真实信息。</p></aside>
  </div></div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'

const profile = reactive<Record<string, any>>({})
const saving = ref(false)
async function load() { try { Object.assign(profile, (await api.profile()).data) } catch (error) { message.error((error as Error).message) } }
async function save() { saving.value = true; try { Object.assign(profile, (await api.saveProfile({ ...profile })).data); message.success('个人档案已保存') } catch (error) { message.error((error as Error).message) } finally { saving.value = false } }
useRefresh(load)
</script>
