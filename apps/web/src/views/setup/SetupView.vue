<template>
  <div class="view active-view setup-view">
    <section class="setup-hero setup-guide-hero">
      <div>
        <span class="pill">首次使用 · 约 5 分钟</span>
        <h2>三步完成首次配置</h2>
        <p>先跑通最短路径，再逐步探索项目库、匹配规则和简历模板。每一步都会根据服务器上的真实状态自动更新。</p>
        <div class="setup-hero-actions">
          <span>{{ completedGuideSteps }}/3 已完成</span>
        </div>
      </div>
      <div class="setup-score"><strong>{{ completedGuideSteps }}/3</strong><span>配置进度</span></div>
    </section>

    <div v-if="error" class="setup-error" role="alert"><strong>无法读取安装状态</strong><span>{{ error }}</span><a-button @click="load">重新连接</a-button></div>

    <section class="setup-guide" aria-label="首次使用向导">
      <nav class="setup-step-rail" aria-label="配置步骤">
        <button v-for="step in guideSteps" :key="step.id" type="button" class="setup-step-tab" :class="{ 'is-active': activeStep === step.id, 'is-complete': step.complete }" :aria-current="activeStep === step.id ? 'step' : undefined" @click="selectStep(step.id)">
          <span class="setup-step-index">{{ step.complete ? '✓' : step.id }}</span>
          <span><strong>{{ step.title }}</strong><small>{{ step.short }}</small></span><i aria-hidden="true"></i>
        </button>
      </nav>

      <div class="setup-guide-stage">
        <transition name="guide-slide" mode="out-in">
          <article v-if="activeStep === 'done'" key="done" class="setup-guide-card">
            <div class="setup-guide-copy">
              <span class="setup-guide-kicker">READY TO START</span>
              <h2>恭喜，首次配置已完成！</h2>
              <p>浏览器扩展、简历和模型均已准备好。接下来前往自动投递，核对筛选条件与投递计划后再启动任务；无需提前手动添加测试职位。</p>
              <div class="setup-guide-status is-complete">
                <span>✓</span>
                <div><strong>已完成 3 项配置</strong><small>可以开始设置自动投递任务</small></div>
              </div>
              <div class="setup-guide-actions">
                <a-button type="primary" @click="go('/automation')">前往自动投递</a-button>
              </div>
            </div>
            <div class="setup-guide-visual" aria-hidden="true">
              <div class="setup-visual-glow"></div><div class="setup-visual-orbit orbit-one"></div><div class="setup-visual-orbit orbit-two"></div>
              <div class="setup-visual-device">
                <div class="setup-device-top"><i></i><i></i><i></i></div>
                <div class="setup-device-content"><span class="visual-shield">✓</span><b>配置完成</b><em>READY</em></div>
              </div>
              <span class="setup-pulse-dot dot-one"></span><span class="setup-pulse-dot dot-two"></span><span class="setup-pulse-dot dot-three"></span>
            </div>
          </article>
          <article v-else :key="activeGuide.id" class="setup-guide-card">
            <div class="setup-guide-copy">
              <span class="setup-guide-kicker">STEP 0{{ activeGuide.id }}</span>
              <h2>{{ activeGuide.title }}</h2><p>{{ activeGuide.description }}</p>
              <div class="setup-guide-status" :class="activeGuide.complete ? 'is-complete' : 'is-pending'">
                <span>{{ activeGuide.complete ? '✓' : '•' }}</span>
                <div><strong>{{ activeGuide.complete ? '本步骤已完成' : activeGuide.statusTitle }}</strong><small>{{ activeGuide.statusText }}</small></div>
              </div>
              <div class="setup-guide-actions">
                <template v-if="activeStep === 1">
                  <a-button type="primary" :href="extensionDownloadUrl" target="_blank" rel="noopener noreferrer">下载浏览器插件</a-button>
                  <a-button v-if="!browserProtocol?.connected" type="primary" :loading="pairingLoading" @click="createPairing">生成六位配对码</a-button>
                  <a-button v-else :loading="loading" @click="load">重新检测连接</a-button>
                  <a-button @click="scrollToBrowserDetails">查看连接说明</a-button>
                </template>
                <a-button v-else-if="activeStep === 2" type="primary" @click="go('/resumes')">{{ activeGuide.complete ? '查看已确认简历' : '导入并确认简历' }}</a-button>
                <template v-else>
                  <a-button type="primary" @click="go('/models')">{{ activeGuide.complete ? '查看模型配置' : '配置并测试模型' }}</a-button>
                  <a-button v-if="setupComplete" @click="activeStep = 'done'">查看完成页</a-button>
                </template>
              </div>
              <p v-if="pairing && activeStep === 1" class="setup-pairing-inline">配对码 <strong>{{ pairing.code }}</strong><small>10 分钟内有效</small></p>
            </div>

            <div class="setup-guide-visual" :class="`is-step-${activeGuide.id}`" aria-hidden="true">
              <div class="setup-visual-glow"></div><div class="setup-visual-orbit orbit-one"></div><div class="setup-visual-orbit orbit-two"></div>
              <div class="setup-visual-device">
                <div class="setup-device-top"><i></i><i></i><i></i></div>
                <div class="setup-device-content">
                  <template v-if="activeGuide.id === 1"><span class="visual-extension">J</span><b>浏览器插件</b><em>{{ browserProtocol?.connected ? 'CONNECTED' : 'PAIRING' }}</em></template>
                  <template v-else-if="activeGuide.id === 2"><span class="visual-document"><i></i><i></i><i></i></span><b>简历识别与确认</b><em>LOCAL ONLY</em></template>
                  <template v-else><span class="visual-model"><i></i><i></i><i></i></span><b>模型连接测试</b><em>ENCRYPTED</em></template>
                </div><span class="setup-visual-scan"></span>
              </div>
              <span class="setup-pulse-dot dot-one"></span><span class="setup-pulse-dot dot-two"></span><span class="setup-pulse-dot dot-three"></span>
            </div>
          </article>
        </transition>
        <div class="setup-guide-progress" role="progressbar" aria-label="首次配置进度" :aria-valuenow="completedGuideSteps" aria-valuemin="0" aria-valuemax="3"><i :style="{ width: `${(completedGuideSteps / 3) * 100}%` }"></i></div>
      </div>
    </section>

    <section v-if="activeStep === 1" id="browser" class="setup-section setup-browser-panel">
      <div class="setup-section-heading"><div><p class="eyebrow">PLUGIN CONNECTION</p><h2>插件连接详情</h2></div><span class="setup-phase">只连接当前账号</span></div>
      <div class="setup-browser-content">
        <div class="browser-pairing-card">
          <h3>{{ browserProtocol?.connected ? '统一 Chrome 扩展已连接' : '在 BOSS 页面完成配对' }}</h3>
          <p>{{ browserProtocol?.connected ? `扩展 ${browserProtocol.extensionVersion || ''} 已接入本地服务，协议 ${browserProtocol.protocolVersion}。` : '先生成配对码，再点击 Chrome 工具栏中的扩展图标，在弹窗中输入服务地址和配对码。配对码仅用于连接本机服务。' }}</p>
          <strong v-if="pairing && !browserProtocol?.connected" class="browser-pairing-code">{{ pairing.code }}</strong>
          <div class="browser-pairing-actions"><a-button type="primary" :href="extensionDownloadUrl" target="_blank" rel="noopener noreferrer">下载最新版插件</a-button><a-button v-if="!browserProtocol?.connected" :loading="pairingLoading" @click="createPairing">生成配对码</a-button><a-button :loading="loading" @click="load">重新检测</a-button></div>
          <p v-if="browserMessage" class="browser-pairing-message">{{ browserMessage }}</p>
        </div>
        <div class="setup-browser-states">
          <div v-for="check in browserChecks" :key="check.key" class="setup-browser-state" :class="`is-${check.status}`"><span class="setup-check-icon">{{ statusIcon(check.status) }}</span><div><strong>{{ check.label }}</strong><p>{{ check.message }}</p></div></div>
        </div>
        <form class="browser-probe-form" @submit.prevent="saveBrowserProbe">
          <p>请核对 BOSS 页面上的账号身份。身份错误会导致使用他人的简历和问候语，采集前系统还会再次校验。</p>
          <label><input v-model="probe.projectExtensionReady" type="checkbox" /> BOSS 页面已加载统一扩展</label>
          <label><input v-model="probe.bossLoggedIn" type="checkbox" /> BOSS 右上角身份与个人档案“{{ profileName || '尚未填写姓名' }}”一致</label>
          <a-button type="primary" html-type="submit" :loading="savingProbe">保存账号确认</a-button>
        </form>
      </div>
    </section>

    <details class="setup-diagnostics">
      <summary><span><b>环境检测明细</b><small>{{ readyCount }} 项成功 · {{ issueCount }} 项需处理</small></span><a-button size="small" :loading="loading" @click.prevent="load">刷新状态</a-button></summary>
      <div class="setup-result-columns">
        <section class="setup-result-group is-ready"><header><div><span>✓</span><strong>检测成功</strong></div><b>{{ readyChecks.length }} 项</b></header><div v-if="!readyChecks.length" class="setup-result-empty">完成检测后在这里显示通过项。</div><article v-for="check in readyChecks" :key="check.key"><span class="setup-check-icon">✓</span><div><strong>{{ check.label }}</strong><p>{{ check.message }}</p></div></article></section>
        <section class="setup-result-group is-blocked"><header><div><span>!</span><strong>需要处理</strong></div><b>{{ issueChecks.length }} 项</b></header><div v-if="!issueChecks.length" class="setup-result-empty">必要项目均已通过。</div><article v-for="check in issueChecks" :key="check.key"><span class="setup-check-icon">{{ statusIcon(check.status) }}</span><div><strong>{{ check.label }}</strong><p>{{ check.message }}</p></div><a-button v-if="check.actionPath" size="small" @click="go(check.actionPath)">{{ check.actionLabel || '去处理' }}</a-button></article></section>
      </div>
    </details>

    <section class="setup-advanced" :class="{ 'is-locked': !setupComplete }">
      <div><p class="eyebrow">AFTER SETUP</p><h2>{{ setupComplete ? '继续探索进阶能力' : '完成首次配置后再探索进阶能力' }}</h2><p>{{ setupComplete ? '现在可以按需要补充项目证据、细化匹配规则，或制作专属简历模板。' : '先完成上面的三项配置，不必在首次使用时理解所有设置。' }}</p></div>
      <div class="setup-advanced-links"><a-button :disabled="!setupComplete" @click="go('/projects')">项目库</a-button><a-button :disabled="!setupComplete" @click="go('/rules')">匹配规则</a-button><a-button :disabled="!setupComplete" @click="go('/templates')">简历模板</a-button></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../services/api'
import { useRefresh } from '../../composables/useRefresh'
import type { BrowserPairing, BrowserProbe, BrowserProtocolStatus, SetupCheckStatus, SetupStatus } from '../../types'

type GuideStepId = 1 | 2 | 3
const router = useRouter()
const extensionDownloadUrl = 'https://github.com/a764506248/Job-Search-Assistant/releases/latest/download/job-search-assistant-chrome-mv3.zip'
const status = ref<SetupStatus>()
const loading = ref(false)
const error = ref('')
const savingProbe = ref(false)
const browserProtocol = ref<BrowserProtocolStatus>()
const pairing = ref<BrowserPairing>()
const pairingLoading = ref(false)
const browserMessage = ref('')
const profileName = ref('')
const activeStep = ref<GuideStepId | 'done'>(1)
let initialized = false

const probe = ref<BrowserProbe>({ projectExtensionReady: false, bossLoggedIn: false, source: 'manual' })
const browserKeys = new Set(['kimi-webbridge', 'project-extension', 'boss-login'])
const browserChecks = computed(() => status.value?.checks.filter(check => browserKeys.has(check.key)) || [])
const readyChecks = computed(() => status.value?.checks.filter(check => check.status === 'ready') || [])
const issueChecks = computed(() => status.value?.checks.filter(check => check.status !== 'ready') || [])
const readyCount = computed(() => readyChecks.value.length)
const issueCount = computed(() => issueChecks.value.length)
const checkReady = (key: string) => status.value?.checks.some(check => check.key === key && check.status === 'ready') || false

const guideSteps = computed(() => [
  { id: 1 as GuideStepId, title: '安装并连接插件', short: '连接已登录的 BOSS 页面', description: '安装统一 Chrome 扩展，通过六位配对码连接本地服务，并确认当前 BOSS 账号身份。', complete: Boolean(browserProtocol.value?.connected) && checkReady('boss-login'), statusTitle: '等待插件连接', statusText: browserProtocol.value?.connected ? '扩展已连接，请继续确认 BOSS 账号身份。' : '生成配对码后，在 Chrome 工具栏的扩展弹窗中输入。' },
  { id: 2 as GuideStepId, title: '导入并确认简历', short: '核对识别结果再写入', description: '上传现有简历，让系统在本机完成结构化识别；核对姓名、目标岗位和项目经历后再确认。', complete: checkReady('resume'), statusTitle: '等待确认简历', statusText: '未确认的识别结果不会进入后续职位分析与材料生成。' },
  { id: 3 as GuideStepId, title: '配置模型', short: '保存并完成连接测试', description: '选择模型服务，填写接口地址与密钥，然后执行连接测试。密钥只保存在你的本地服务中。', complete: checkReady('model'), statusTitle: '等待模型验证', statusText: '只有通过连接测试的模型才会用于 AI 分析。' },
])
const activeGuide = computed(() => guideSteps.value.find(step => step.id === activeStep.value) || guideSteps.value[0])
const completedGuideSteps = computed(() => guideSteps.value.filter(step => step.complete).length)
const setupComplete = computed(() => completedGuideSteps.value === 3)

function statusIcon(value: SetupCheckStatus) { return value === 'ready' ? '✓' : value === 'blocked' ? '!' : '…' }
function go(path: string) { router.push(path) }
function selectStep(step: GuideStepId) { activeStep.value = step }
function scrollToBrowserDetails() { document.querySelector('#browser')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [setupResult, browserResult, profileResult] = await Promise.all([api.setupStatus(), api.browserStatus(), api.profile()])
    status.value = setupResult
    browserProtocol.value = browserResult
    profileName.value = String(profileResult.data.displayName || '').trim()
    if (!initialized || setupComplete.value) {
      activeStep.value = guideSteps.value.find(step => !step.complete)?.id || 'done'
      initialized = true
    }
  } catch (reason) { error.value = (reason as Error).message }
  finally { loading.value = false }
}

async function createPairing() {
  pairingLoading.value = true; browserMessage.value = ''
  try { pairing.value = await api.createBrowserPairing() }
  catch (reason) { browserMessage.value = (reason as Error).message }
  finally { pairingLoading.value = false }
}

async function saveBrowserProbe() {
  savingProbe.value = true
  try { await api.saveBrowserProbe(probe.value); await load() }
  catch (reason) { error.value = (reason as Error).message }
  finally { savingProbe.value = false }
}

useRefresh(load)
</script>
