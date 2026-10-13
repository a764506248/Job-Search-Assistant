<template>
  <main class="landing-page">
    <header class="landing-nav">
      <a class="landing-brand" href="#top" aria-label="Job Search Assistant 首页">
        <span>J</span>
        <strong>Job Search Assistant</strong>
      </a>
      <nav aria-label="首页导航">
        <a href="#features">功能</a>
        <a href="#workflow">使用流程</a>
        <a href="#privacy">隐私安全</a>
        <a href="#source">免费使用</a>
      </nav>
      <a class="repo-entry" href="https://github.com/a764506248/Job-Search-Assistant" target="_blank" rel="noreferrer" aria-label="在 GitHub 查看源代码">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2C6.48 2 2 6.59 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49 0-.24-.01-1.05-.01-1.9-2.78.62-3.37-1.21-3.37-1.21-.45-1.18-1.11-1.49-1.11-1.49-.91-.64.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.12 2.91.85.09-.66.35-1.12.63-1.37-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05A9.3 9.3 0 0 1 12 6.16a9.3 9.3 0 0 1 2.5.35c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.93-2.34 4.8-4.57 5.05.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.59.69.49A10.25 10.25 0 0 0 22 12.25C22 6.59 17.52 2 12 2Z"/></svg>
        GitHub
      </a>
      <button class="nav-entry" @click="enterProduct">{{ entryLabel }}</button>
    </header>

    <section id="top" class="hero landing-section">
      <div class="hero-glow glow-one"></div>
      <div class="hero-glow glow-two"></div>
      <div class="hero-copy">
        <p class="landing-kicker"><i></i> 免费使用 · 代码公开 · 本地优先</p>
        <h1>把海投交给助手<br /><em>把选择留给自己</em></h1>
        <p class="hero-description">
          自动采集职位、理解简历、分析匹配度并准备沟通内容。
          真正投递前由你确认，少做重复操作，把时间留给更值得的机会。
        </p>
        <div class="hero-actions">
          <button class="primary-action" @click="enterProduct">{{ entryLabel }} <span>→</span></button>
          <a class="secondary-action github-action" href="https://github.com/a764506248/Job-Search-Assistant" target="_blank" rel="noreferrer">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2C6.48 2 2 6.59 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49 0-.24-.01-1.05-.01-1.9-2.78.62-3.37-1.21-3.37-1.21-.45-1.18-1.11-1.49-1.11-1.49-.91-.64.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.12 2.91.85.09-.66.35-1.12.63-1.37-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05A9.3 9.3 0 0 1 12 6.16a9.3 9.3 0 0 1 2.5.35c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.93-2.34 4.8-4.57 5.05.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.59.69.49A10.25 10.25 0 0 0 22 12.25C22 6.59 17.52 2 12 2Z"/></svg>
            GitHub 源代码
          </a>
          <a class="workflow-link" href="#workflow">使用流程 ↓</a>
        </div>
        <div class="hero-promises">
          <span><b>✓</b> 数据本地保存</span>
          <span><b>✓</b> 投递前人工确认</span>
          <span><b>✓</b> 每个账号独立隔离</span>
        </div>
      </div>

      <div class="product-preview" aria-label="产品自动投递流程预览">
        <div class="preview-window">
          <div class="window-bar"><i></i><i></i><i></i><span>自动投递工作台</span></div>
          <div class="preview-body">
            <aside class="preview-sidebar">
              <div class="mini-logo">J</div>
              <span class="active"></span><span></span><span></span><span></span><span></span>
            </aside>
            <div class="preview-content">
              <div class="preview-heading"><div><small>AUTOMATION</small><b>更精准地找到合适职位</b></div><button>开始分析</button></div>
              <div class="pipeline">
                <div class="done"><b>1</b><span>采集职位<small>120 个</small></span></div>
                <i>→</i>
                <div class="done"><b>2</b><span>AI 分析<small>匹配规则</small></span></div>
                <i>→</i>
                <div class="current"><b>3</b><span>人工确认<small>安全门</small></span></div>
                <i>→</i>
                <div><b>4</b><span>执行投递<small>可追踪</small></span></div>
              </div>
              <div class="preview-grid">
                <div class="match-card">
                  <div class="score-ring"><strong>86</strong><small>匹配度</small></div>
                  <div><span class="match-tag">建议投递</span><b>AI Agent 开发工程师</b><small>技能匹配 · 薪资符合 · 方向一致</small></div>
                </div>
                <div class="stats-card">
                  <small>今日进展</small>
                  <div><b>24</b><span>已采集</span></div>
                  <div><b>7</b><span>待确认</span></div>
                  <div><b>5</b><span>已投递</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="floating-note note-one"><i>✓</i><span><b>规则检查通过</b><small>薪资与方向均符合</small></span></div>
        <div class="floating-note note-two"><span class="ai-spark">✦</span><span><b>AI 分析完成</b><small>已生成个性化问候语</small></span></div>
      </div>
    </section>

    <section class="trust-strip">
      <span>不是盲目海投</span><i></i><span>不是替你做决定</span><i></i><span>是让每次投递更有依据</span>
    </section>

    <section id="features" class="landing-section features-section">
      <div class="section-heading">
        <p class="landing-kicker"><i></i> 从发现职位到开始沟通</p>
        <h2>重复的交给系统，<br />重要的留给你判断</h2>
        <p>它不只帮你“点投递”，而是先理解你，再判断职位是否值得投入时间。</p>
      </div>
      <div class="feature-grid">
        <article v-for="feature in features" :key="feature.title" class="feature-card">
          <span class="feature-icon" v-html="feature.icon"></span>
          <small>{{ feature.eyebrow }}</small>
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.description }}</p>
          <div class="feature-demo" :class="feature.demo">
            <template v-if="feature.demo === 'demo-jobs'">
              <span v-for="value in [86, 72, 48]" :key="value"><i :style="{ width: `${value}%` }"></i><b>{{ value }}</b></span>
            </template>
            <template v-else-if="feature.demo === 'demo-resume'">
              <i></i><div><span></span><span></span><span></span></div><b>✓</b>
            </template>
            <template v-else-if="feature.demo === 'demo-rules'">
              <span>期望薪资 <b>通过</b></span><span>目标方向 <b>通过</b></span>
            </template>
            <template v-else-if="feature.demo === 'demo-message'">
              <span>你好，看到贵司正在招聘 AI Agent…</span><i></i>
            </template>
            <template v-else-if="feature.demo === 'demo-confirm'">
              <button>暂不投递</button><button>确认投递</button>
            </template>
            <template v-else>
              <span><b>采集</b> 24</span><span><b>通过</b> 7</span><span><b>投递</b> 5</span>
            </template>
          </div>
        </article>
      </div>
    </section>

    <section class="analysis-showcase landing-section">
      <div class="showcase-copy">
        <p class="landing-kicker light"><i></i> 不只看关键词</p>
        <h2>先分析值不值得投，<br />再决定要不要行动</h2>
        <p>系统会把职位要求与你的简历、项目经历和个人规则放在一起分析，给出清楚的判断依据，而不是只给一个模糊分数。</p>
        <ul>
          <li><span>01</span><div><b>硬性条件先过滤</b><small>薪资、城市、经验和学历要求不合适，直接说明原因。</small></div></li>
          <li><span>02</span><div><b>项目经历有据可查</b><small>告诉你哪些经历能支撑岗位要求，哪些能力仍有缺口。</small></div></li>
          <li><span>03</span><div><b>沟通内容因岗而异</b><small>根据岗位亮点准备问候语，避免千篇一律的模板。</small></div></li>
        </ul>
      </div>
      <div class="analysis-card">
        <div class="analysis-card-head"><span>职位分析报告</span><small>刚刚完成</small></div>
        <div class="analysis-title"><div><b>AI Agent 开发工程师</b><small>北京 · 35–55K · 3–5 年</small></div><span>86<small>/ 100</small></span></div>
        <div class="analysis-bars">
          <label>技能匹配 <span><i style="width: 92%"></i></span><b>92</b></label>
          <label>经验相关 <span><i style="width: 84%"></i></span><b>84</b></label>
          <label>方向一致 <span><i style="width: 88%"></i></span><b>88</b></label>
        </div>
        <div class="evidence-card"><span>✓</span><div><b>建议投递</b><p>你的 LangGraph、RAG 和 Python/FastAPI 经历与岗位核心要求高度相关。</p></div></div>
        <div class="skill-chips"><span>LangGraph</span><span>RAG</span><span>Python</span><span>FastAPI</span></div>
      </div>
    </section>

    <section id="workflow" class="landing-section workflow-section">
      <div class="section-heading compact">
        <p class="landing-kicker"><i></i> 四步开始</p>
        <h2>第一次使用，也不用研究半天</h2>
        <p>跟着产品里的向导做完四步，就能用一个真实职位完成安全测试。</p>
      </div>
      <div class="workflow-line">
        <article v-for="(step, index) in steps" :key="step.title">
          <div class="step-number">0{{ index + 1 }}</div>
          <span class="step-visual" :class="`visual-${index + 1}`"><i></i><b>{{ step.symbol }}</b></span>
          <h3>{{ step.title }}</h3>
          <p>{{ step.description }}</p>
          <small>{{ step.note }}</small>
        </article>
      </div>
    </section>

    <section id="privacy" class="privacy-section landing-section">
      <div class="privacy-copy">
        <p class="landing-kicker light"><i></i> LOCAL FIRST</p>
        <h2>你的求职数据，<br />由你自己掌控</h2>
        <p>简历、职位快照、匹配规则和投递记录优先保存在你自己的服务中。系统在真正执行前设置确认环节，让自动化保持在可控范围内。</p>
        <button class="light-action" @click="enterProduct">开始配置 <span>→</span></button>
      </div>
      <div class="privacy-grid">
        <article><span>⌂</span><div><b>本地优先</b><p>核心求职资料保存在自己的设备或服务器，不依赖公共云端账号。</p></div></article>
        <article><span>◎</span><div><b>账号隔离</b><p>不同用户的职位、简历和去重记录按用户分别管理。</p></div></article>
        <article><span>✓</span><div><b>投递安全门</b><p>候选企业、岗位和发送内容会在执行前交给你确认。</p></div></article>
        <article><span>↻</span><div><b>过程可追踪</b><p>采集、分析、确认和投递状态都有记录，失败也能看到原因。</p></div></article>
      </div>
    </section>

    <section id="source" class="source-section landing-section">
      <div class="source-mark">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2C6.48 2 2 6.59 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49 0-.24-.01-1.05-.01-1.9-2.78.62-3.37-1.21-3.37-1.21-.45-1.18-1.11-1.49-1.11-1.49-.91-.64.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.12 2.91.85.09-.66.35-1.12.63-1.37-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05A9.3 9.3 0 0 1 12 6.16a9.3 9.3 0 0 1 2.5.35c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.93-2.34 4.8-4.57 5.05.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.59.69.49A10.25 10.25 0 0 0 22 12.25C22 6.59 17.52 2 12 2Z"/></svg>
      </div>
      <div class="source-copy">
        <p class="landing-kicker"><i></i> SOURCE AVAILABLE</p>
        <h2>个人非商业使用免费，<br />每一行代码都可以查看</h2>
        <p>项目源代码托管在 GitHub。你可以检查实现、提交问题、参与改进，也可以在许可证允许的范围内自行部署和修改。</p>
        <div class="source-points"><span>✓ 源代码公开</span><span>✓ 可自行部署</span><span>✓ 欢迎 Issue 与贡献</span></div>
      </div>
      <div class="source-action">
        <a href="https://github.com/a764506248/Job-Search-Assistant" target="_blank" rel="noreferrer">在 GitHub 查看项目 <span>↗</span></a>
        <small>遵循 PolyForm Noncommercial 1.0.0<br />个人学习及其他非商业用途免费</small>
      </div>
    </section>

    <section class="final-cta landing-section">
      <p class="landing-kicker"><i></i> 少一点重复，多一点选择</p>
      <h2>准备好更认真地找下一份工作了吗？</h2>
      <p>先完成一次安全测试，再决定如何把它放进你的求职流程。</p>
      <button class="primary-action" @click="enterProduct">{{ entryLabel }} <span>→</span></button>
    </section>

    <footer class="landing-footer">
      <a class="landing-brand footer-brand" href="#top"><span>J</span><strong>Job Search Assistant</strong></a>
      <p>更懂你的本地 AI 求职助手</p>
      <div><a href="#features">功能</a><a href="#workflow">流程</a><a href="#privacy">隐私</a><a href="https://github.com/a764506248/Job-Search-Assistant" target="_blank" rel="noreferrer">GitHub</a><button @click="enterProduct">{{ entryLabel }}</button></div>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const isSignedIn = computed(() => Boolean(localStorage.getItem('jsa_access_token')))
const entryLabel = computed(() => isSignedIn.value ? '进入控制台' : '登录使用')

function enterProduct() {
  router.push(isSignedIn.value ? '/automation' : '/login')
}

const features = [
  { eyebrow: 'JOB CAPTURE', title: '职位自动采集', description: '从搜索结果中整理职位、公司、薪资和要求，免去反复复制粘贴。', demo: 'demo-jobs', icon: '⌕' },
  { eyebrow: 'RESUME', title: '读懂你的简历', description: '识别技能、经历与项目亮点，建立真正属于你的求职资料库。', demo: 'demo-resume', icon: '▤' },
  { eyebrow: 'MATCHING', title: '规则与 AI 双重判断', description: '先检查硬性条件，再结合经历分析匹配度，判断结果更有依据。', demo: 'demo-rules', icon: '◇' },
  { eyebrow: 'GREETING', title: '生成个性化问候语', description: '根据岗位要求引用你的相关经历，不再给所有招聘者发送同一句话。', demo: 'demo-message', icon: '✦' },
  { eyebrow: 'CONTROL', title: '投递前由你确认', description: '系统准备候选清单和内容，你决定哪些企业值得真正发出。', demo: 'demo-confirm', icon: '✓' },
  { eyebrow: 'TRACKING', title: '每一步都有记录', description: '采集、分析、通过、失败和投递结果集中展示，求职进度不再混乱。', demo: 'demo-stats', icon: '↗' },
]

const steps = [
  { symbol: '⌁', title: '连接浏览器扩展', description: '让本地服务读取你已经登录的职位页面。', note: '保留现有登录状态' },
  { symbol: '▤', title: '导入并确认简历', description: 'AI 帮你整理内容，你确认后再写入资料库。', note: 'PDF、DOCX、TXT、Markdown' },
  { symbol: '✦', title: '配置 AI 模型', description: '选择你自己的模型服务，用于简历与职位分析。', note: '支持主模型与兜底模型' },
  { symbol: '▶', title: '测试一个职位', description: '先跑一次完整流程，确认结果后再逐步扩大。', note: '安全地验证整个链路' },
]
</script>

<style scoped>
.landing-page { --landing-green: #0d674f; --landing-dark: #0c211b; --landing-mint: #dff5ea; --landing-line: #dfeae5; min-height: 100vh; padding: 0; overflow: hidden; background: #fbfdfb; color: #13211c; }
.landing-page button, .landing-page a { -webkit-tap-highlight-color: transparent; }
.landing-section { width: min(1180px, calc(100% - 48px)); margin-inline: auto; }
.landing-nav { position: relative; z-index: 20; width: min(1240px, calc(100% - 48px)); height: 78px; margin: 0 auto; display: flex; align-items: center; gap: 44px; }
.landing-brand { display: inline-flex; align-items: center; gap: 10px; color: inherit; text-decoration: none; }
.landing-brand > span { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; background: var(--landing-dark); color: #bdf3db; font: 800 19px/1 Georgia, serif; }
.landing-brand strong { font-size: 15px; letter-spacing: -.01em; }
.landing-nav nav { display: flex; gap: 30px; }
.landing-nav nav a, .landing-footer a { color: #59665f; text-decoration: none; font-size: 13px; }
.landing-nav nav a:hover, .landing-footer a:hover { color: var(--landing-green); }
.repo-entry { margin-left: auto; display: inline-flex; align-items: center; gap: 7px; color: #405048; text-decoration: none; font-size: 12px; font-weight: 700; }
.repo-entry svg, .github-action svg { width: 18px; height: 18px; fill: currentColor; }
.nav-entry { margin-left: auto; padding: 10px 18px; border: 1px solid #183c31; border-radius: 999px; background: var(--landing-dark); color: white; font-size: 13px; font-weight: 700; cursor: pointer; transition: .2s ease; }
.repo-entry + .nav-entry { margin-left: 0; }
.nav-entry:hover, .primary-action:hover { transform: translateY(-2px); box-shadow: 0 10px 26px rgba(13,103,79,.2); }
.hero { position: relative; min-height: 760px; padding: 96px 0 80px; display: grid; grid-template-columns: .88fr 1.12fr; align-items: center; gap: 56px; }
.hero-glow { position: absolute; z-index: 0; border-radius: 50%; filter: blur(4px); pointer-events: none; }
.glow-one { width: 560px; height: 560px; right: -170px; top: 50px; background: radial-gradient(circle, rgba(145,238,197,.34), rgba(221,248,236,.1) 55%, transparent 72%); }
.glow-two { width: 300px; height: 300px; left: -220px; top: 210px; background: radial-gradient(circle, rgba(146,232,207,.22), transparent 70%); }
.hero-copy, .product-preview { position: relative; z-index: 1; }
.landing-kicker { margin: 0 0 24px; display: flex; align-items: center; gap: 9px; color: var(--landing-green); font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.landing-kicker i { width: 21px; height: 1px; background: currentColor; }
.landing-kicker.light { color: #94dbc2; }
.hero h1 { margin: 0; font: 700 clamp(45px, 5.2vw, 70px)/1.08 Georgia, "Noto Serif SC", serif; letter-spacing: -.055em; }
.hero h1 em { color: var(--landing-green); font-style: normal; }
.hero-description { max-width: 540px; margin: 28px 0 0; color: #637169; font-size: 16px; line-height: 1.9; }
.hero-actions { margin-top: 34px; display: flex; align-items: center; gap: 13px; }
.primary-action, .secondary-action, .light-action { min-height: 48px; padding: 0 21px; border-radius: 11px; display: inline-flex; align-items: center; justify-content: center; gap: 22px; font-size: 14px; font-weight: 750; text-decoration: none; cursor: pointer; transition: .2s ease; }
.primary-action { border: 0; background: var(--landing-green); color: #fff; }
.secondary-action { border: 1px solid var(--landing-line); background: #fff; color: #25342e; }
.github-action { gap: 9px; }
.workflow-link { color: #547067; font-size: 12px; font-weight: 700; text-decoration: none; }
.hero-promises { margin-top: 25px; display: flex; flex-wrap: wrap; gap: 18px; color: #718078; font-size: 11px; }
.hero-promises span { display: flex; align-items: center; gap: 5px; }
.hero-promises b { color: var(--landing-green); }
.product-preview { transform: perspective(1400px) rotateY(-4deg) rotateX(1deg); }
.preview-window { overflow: hidden; border: 1px solid rgba(116,154,139,.25); border-radius: 20px; background: white; box-shadow: 0 34px 90px rgba(24,76,59,.18), 0 4px 18px rgba(24,76,59,.08); }
.window-bar { height: 42px; padding: 0 15px; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid #edf2ef; color: #8a9992; font-size: 10px; }
.window-bar i { width: 7px; height: 7px; border-radius: 50%; background: #dbe4df; }
.window-bar i:first-child { background: #86cdb4; }
.window-bar span { margin-left: 8px; }
.preview-body { min-height: 410px; display: grid; grid-template-columns: 60px 1fr; }
.preview-sidebar { padding: 16px 12px; background: #102c23; display: flex; flex-direction: column; align-items: center; gap: 17px; }
.mini-logo { width: 27px; height: 27px; margin-bottom: 11px; border-radius: 8px; display: grid; place-items: center; background: #cdf1e2; color: #124b3b; font: 800 13px Georgia, serif; }
.preview-sidebar > span { width: 26px; height: 6px; border-radius: 8px; background: rgba(219,242,232,.19); }
.preview-sidebar > span.active { height: 25px; background: rgba(219,242,232,.16); border: 1px solid rgba(219,242,232,.14); }
.preview-content { padding: 24px 22px; background: #f7faf8; }
.preview-heading { display: flex; align-items: center; justify-content: space-between; gap: 15px; }
.preview-heading > div { display: grid; gap: 5px; }
.preview-heading small { color: var(--landing-green); font-size: 7px; letter-spacing: .15em; }
.preview-heading b { font: 700 15px Georgia, "Noto Serif SC", serif; }
.preview-heading button { border: 0; border-radius: 7px; padding: 8px 12px; background: var(--landing-green); color: white; font-size: 8px; }
.pipeline { margin-top: 20px; padding: 13px; border: 1px solid #e1ebe6; border-radius: 10px; background: #fff; display: grid; grid-template-columns: repeat(7, auto); align-items: center; gap: 7px; }
.pipeline > div { display: flex; align-items: center; gap: 7px; opacity: .46; }
.pipeline > div.done, .pipeline > div.current { opacity: 1; }
.pipeline > div.current { padding: 7px; border-radius: 8px; background: #e5f5ee; }
.pipeline b { width: 20px; height: 20px; flex: 0 0 auto; border-radius: 50%; display: grid; place-items: center; background: #dce5e1; color: #64736c; font-size: 8px; }
.pipeline .done b, .pipeline .current b { background: var(--landing-green); color: #fff; }
.pipeline span { display: grid; gap: 2px; font-size: 8px; font-weight: 700; white-space: nowrap; }
.pipeline small { color: #87938d; font-size: 6px; font-weight: 400; }
.pipeline > i { color: #a6b4ad; font-size: 10px; font-style: normal; }
.preview-grid { margin-top: 15px; display: grid; grid-template-columns: 1.5fr .8fr; gap: 12px; }
.match-card, .stats-card { min-height: 160px; padding: 18px; border: 1px solid #e1eae5; border-radius: 12px; background: #fff; }
.match-card { display: flex; align-items: center; gap: 17px; }
.score-ring { width: 83px; height: 83px; flex: 0 0 auto; border-radius: 50%; display: grid; place-content: center; text-align: center; background: radial-gradient(circle at center, #fff 59%, transparent 60%), conic-gradient(var(--landing-green) 0 86%, #e6eee9 86%); }
.score-ring strong { color: var(--landing-green); font: 700 23px Georgia, serif; }
.score-ring small { color: #809087; font-size: 6px; }
.match-card > div:last-child { min-width: 0; display: grid; gap: 8px; }
.match-card b { font-size: 11px; }
.match-card small { color: #839088; font-size: 7px; line-height: 1.5; }
.match-tag { width: fit-content; padding: 4px 6px; border-radius: 999px; background: #e2f4ec; color: var(--landing-green); font-size: 7px; font-weight: 700; }
.stats-card { display: grid; grid-template-columns: repeat(3,1fr); align-content: start; gap: 12px 6px; }
.stats-card > small { grid-column: 1/-1; color: #829088; font-size: 7px; }
.stats-card div { display: grid; gap: 5px; }
.stats-card b { color: var(--landing-green); font: 700 18px Georgia, serif; }
.stats-card span { color: #89958f; font-size: 6px; }
.floating-note { position: absolute; padding: 12px 15px; border: 1px solid rgba(184,214,202,.75); border-radius: 11px; background: rgba(255,255,255,.94); backdrop-filter: blur(9px); display: flex; align-items: center; gap: 10px; box-shadow: 0 16px 38px rgba(20,72,55,.14); }
.floating-note > span:last-child { display: grid; gap: 3px; }
.floating-note b { font-size: 9px; }.floating-note small { color: #819087; font-size: 7px; }
.note-one { left: -38px; bottom: 42px; }.note-one > i { width: 23px; height: 23px; border-radius: 50%; display: grid; place-items: center; background: #e0f4eb; color: var(--landing-green); font-size: 10px; font-style: normal; }
.note-two { right: -30px; top: 73px; }.ai-spark { width: 25px; height: 25px; border-radius: 8px; display: grid !important; place-items: center; background: var(--landing-green); color: white; }
.trust-strip { min-height: 92px; padding: 24px; display: flex; align-items: center; justify-content: center; gap: 32px; background: var(--landing-dark); color: #d9e9e2; font: 600 14px Georgia, "Noto Serif SC", serif; }
.trust-strip i { width: 4px; height: 4px; border-radius: 50%; background: #60bd9b; }
.features-section { padding-block: 125px; }
.section-heading { position: relative; max-width: 690px; margin-bottom: 55px; }
.section-heading h2, .showcase-copy h2, .privacy-copy h2, .final-cta h2 { margin: 0; font: 700 clamp(34px,4vw,52px)/1.2 Georgia, "Noto Serif SC", serif; letter-spacing: -.035em; }
.section-heading > p:last-child { max-width: 580px; margin: 20px 0 0; color: #6b7871; line-height: 1.8; }
.feature-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; }
.feature-card { position: relative; min-height: 335px; padding: 30px; overflow: hidden; border: 1px solid var(--landing-line); border-radius: 18px; background: white; transition: .25s ease; }
.feature-card:hover { transform: translateY(-4px); border-color: #b9d9cc; box-shadow: 0 20px 45px rgba(28,75,59,.08); }
.feature-icon { width: 40px; height: 40px; border-radius: 11px; display: grid; place-items: center; background: #e6f6ef; color: var(--landing-green); font-size: 18px; }
.feature-card > small { display: block; margin-top: 25px; color: #6b9a89; font-size: 9px; font-weight: 800; letter-spacing: .13em; }
.feature-card h3 { margin: 7px 0 11px; font-size: 20px; }
.feature-card > p { margin: 0; color: #6f7b75; font-size: 13px; line-height: 1.75; }
.feature-demo { position: absolute; left: 30px; right: 30px; bottom: 28px; min-height: 48px; }
.demo-jobs { display: grid; gap: 6px; }.demo-jobs span { height: 7px; display: flex; align-items: center; gap: 8px; border-radius: 10px; background: #eef3f0; }.demo-jobs i { height: 100%; border-radius: 10px; background: #74bea3; }.demo-jobs b { color: #64736c; font-size: 8px; }
.demo-resume { height: 54px; padding: 8px; border: 1px solid #e3ebe7; border-radius: 8px; display: grid; grid-template-columns: 36px 1fr 22px; gap: 8px; align-items: center; }.demo-resume > i { height: 36px; border-radius: 5px; background: linear-gradient(135deg,#d6eee4,#f6faf8); }.demo-resume div { display: grid; gap: 5px; }.demo-resume div span { height: 4px; border-radius: 4px; background: #dce7e2; }.demo-resume div span:last-child { width: 65%; }.demo-resume b { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items:center; background: #dff4ea; color: var(--landing-green); font-size: 9px; }
.demo-rules { display: flex; gap: 7px; }.demo-rules span { flex: 1; padding: 10px; border-radius: 8px; background: #f3f7f5; color: #77837d; font-size: 8px; }.demo-rules b { display: block; margin-top: 5px; color: var(--landing-green); }
.demo-message { padding: 11px 14px; border-radius: 12px 12px 3px 12px; background: #dff2ea; color: #376052; font-size: 8px; line-height: 1.6; }.demo-message i { display: inline-block; width: 1px; height: 10px; margin-left: 2px; background: var(--landing-green); animation: blink 1s steps(2) infinite; }
.demo-confirm { display: flex; justify-content: flex-end; gap: 7px; }.demo-confirm button { padding: 9px 11px; border: 1px solid #d8e2dd; border-radius: 7px; background: white; color: #617169; font-size: 8px; }.demo-confirm button:last-child { border-color: var(--landing-green); background: var(--landing-green); color: white; }
.demo-stats { display: grid; grid-template-columns: repeat(3,1fr); gap: 7px; }.demo-stats span { padding: 9px; border-radius: 8px; background: #f2f7f4; color: var(--landing-green); font: 700 16px Georgia,serif; }.demo-stats b { display:block; margin-bottom:4px; color:#7b8881; font:500 7px Inter,sans-serif; }
.analysis-showcase { width: min(1240px, calc(100% - 48px)); padding: 75px; border-radius: 28px; background: linear-gradient(135deg,#0b3025,#0c5b46); color: white; display: grid; grid-template-columns: 1fr .9fr; gap: 90px; align-items: center; box-shadow: 0 35px 80px rgba(13,64,48,.16); }
.showcase-copy > p:not(.landing-kicker) { margin: 23px 0 30px; color: #b7d2c7; line-height: 1.85; }
.showcase-copy ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 17px; }
.showcase-copy li { display: grid; grid-template-columns: 31px 1fr; gap: 12px; align-items: start; }
.showcase-copy li > span { color: #74c5a8; font: 700 11px Georgia, serif; }
.showcase-copy li div { display: grid; gap: 5px; }.showcase-copy li b { font-size: 13px; }.showcase-copy li small { color: #9ebbb0; font-size: 11px; line-height: 1.55; }
.analysis-card { padding: 27px; border: 1px solid rgba(255,255,255,.34); border-radius: 18px; background: rgba(255,255,255,.96); color: #193027; box-shadow: 0 24px 50px rgba(0,0,0,.18); transform: rotate(1.2deg); }
.analysis-card-head { padding-bottom: 16px; border-bottom: 1px solid #e6ece8; display: flex; justify-content: space-between; }.analysis-card-head span { font-weight: 800; }.analysis-card-head small { color: #87938d; }
.analysis-title { margin: 20px 0; display: flex; align-items: center; justify-content: space-between; }.analysis-title > div { display:grid; gap:7px; }.analysis-title b { font-size: 17px; }.analysis-title small { color:#7d8a83; font-size:10px; }.analysis-title > span { color:var(--landing-green); font:700 35px Georgia,serif; }.analysis-title > span small { font-size:10px; }
.analysis-bars { display:grid; gap:10px; }.analysis-bars label { display:grid; grid-template-columns:70px 1fr 24px; gap:9px; align-items:center; color:#65736c; font-size:9px; }.analysis-bars label > span { height:7px; overflow:hidden; border-radius:9px; background:#edf2ef; }.analysis-bars i { display:block; height:100%; border-radius:9px; background:#62b997; }.analysis-bars b { color:#315344; }
.evidence-card { margin-top:19px; padding:14px; border-radius:10px; background:#e8f6ef; display:flex; gap:10px; }.evidence-card > span { width:23px; height:23px; flex:0 0 auto; border-radius:50%; display:grid; place-items:center; background:var(--landing-green); color:white; font-size:10px; }.evidence-card div { display:grid; gap:4px; }.evidence-card b { color:var(--landing-green); font-size:11px; }.evidence-card p { margin:0; color:#5f7169; font-size:9px; line-height:1.55; }
.skill-chips { margin-top:14px; display:flex; flex-wrap:wrap; gap:6px; }.skill-chips span { padding:5px 8px; border:1px solid #dce6e1; border-radius:999px; color:#607069; font-size:8px; }
.workflow-section { padding-block: 135px; }.section-heading.compact { max-width:760px; margin-inline:auto; text-align:center; }.section-heading.compact .landing-kicker { justify-content:center; }.section-heading.compact > p:last-child { margin-inline:auto; }
.workflow-line { position:relative; display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }.workflow-line::before { content:""; position:absolute; left:12%; right:12%; top:103px; border-top:1px dashed #b9cec5; }
.workflow-line article { position:relative; z-index:1; min-height:340px; padding:25px 22px; border:1px solid var(--landing-line); border-radius:17px; background:#fff; text-align:center; }
.step-number { color:#8cab9f; font:700 10px Georgia,serif; text-align:left; }.step-visual { width:100px; height:100px; margin:25px auto 27px; border-radius:50%; display:grid; place-items:center; background:#e7f6ef; color:var(--landing-green); font-size:29px; }.step-visual b { position:relative; z-index:1; }.step-visual i { position:absolute; width:74px; height:74px; border:1px dashed #95c9b5; border-radius:50%; animation:spin 13s linear infinite; }
.workflow-line h3 { margin:0 0 10px; font-size:17px; }.workflow-line p { min-height:44px; margin:0; color:#6c7972; font-size:12px; line-height:1.65; }.workflow-line small { display:block; margin-top:17px; color:#8a9790; font-size:9px; }
.privacy-section { width:min(1240px,calc(100% - 48px)); padding:80px; border-radius:28px; background:#10261f; color:white; display:grid; grid-template-columns:.8fr 1.2fr; gap:80px; align-items:center; }
.privacy-copy > p:not(.landing-kicker) { margin:24px 0 30px; color:#a9c1b7; line-height:1.85; }.light-action { border:0; background:#e1f6ed; color:#0b513e; }
.privacy-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }.privacy-grid article { min-height:155px; padding:22px; border:1px solid rgba(255,255,255,.1); border-radius:14px; background:rgba(255,255,255,.055); display:flex; gap:14px; }.privacy-grid article > span { width:33px; height:33px; flex:0 0 auto; border-radius:9px; display:grid; place-items:center; background:rgba(127,213,181,.13); color:#8bd8bc; }.privacy-grid article div { display:grid; align-content:start; gap:8px; }.privacy-grid b { font-size:13px; }.privacy-grid p { margin:0; color:#92ada2; font-size:10px; line-height:1.7; }
.source-section { margin-top: 24px; padding: 58px 64px; border: 1px solid #cee3da; border-radius: 24px; background: linear-gradient(125deg,#edf9f3,#f9fcfa); display: grid; grid-template-columns: 74px minmax(0,1fr) auto; align-items: center; gap: 32px; }
.source-mark { width: 66px; height: 66px; border-radius: 19px; display: grid; place-items: center; background: var(--landing-dark); box-shadow: 0 16px 35px rgba(12,33,27,.15); }.source-mark svg { width: 35px; height: 35px; fill: #dff5ea; }
.source-copy .landing-kicker { margin-bottom: 12px; }.source-copy h2 { margin: 0; font: 700 30px/1.3 Georgia,"Noto Serif SC",serif; }.source-copy > p:last-of-type { max-width: 650px; margin: 15px 0 0; color: #66756d; font-size: 13px; line-height: 1.75; }.source-points { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 17px; color: #507064; font-size: 11px; }
.source-action { min-width: 230px; display: grid; justify-items: start; gap: 13px; }.source-action a { width: 100%; padding: 14px 17px; border-radius: 10px; background: var(--landing-green); color: white; display: flex; justify-content: space-between; gap: 18px; text-decoration: none; font-size: 12px; font-weight: 750; }.source-action small { color: #7e8c85; font-size: 9px; line-height: 1.6; }
.final-cta { padding-block:145px; display:flex; flex-direction:column; align-items:center; text-align:center; }.final-cta .landing-kicker { justify-content:center; }.final-cta > p:not(.landing-kicker) { margin:20px 0 30px; color:#6c7972; }.final-cta .primary-action { min-width:160px; }
.landing-footer { min-height:180px; padding:44px max(24px,calc((100% - 1180px)/2)); border-top:1px solid var(--landing-line); background:#f3f8f5; display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:35px; }.footer-brand > span { background:var(--landing-green); }.landing-footer > p { margin:0; color:#829087; font-size:12px; }.landing-footer > div { display:flex; align-items:center; gap:22px; }.landing-footer button { border:0; background:transparent; color:var(--landing-green); font-size:13px; font-weight:700; cursor:pointer; }
@keyframes blink { 50% { opacity:0; } } @keyframes spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion:reduce) { .landing-page * { scroll-behavior:auto !important; animation:none !important; transition:none !important; } }
@media (max-width:980px) { .landing-nav nav { display:none; }.hero { min-height:auto; padding-top:70px; grid-template-columns:1fr; }.hero-copy { max-width:720px; text-align:center; margin:auto; }.landing-kicker,.hero-actions,.hero-promises { justify-content:center; }.hero-description { margin-inline:auto; }.product-preview { width:min(720px,100%); margin:10px auto 0; transform:none; }.feature-grid { grid-template-columns:repeat(2,1fr); }.analysis-showcase,.privacy-section { padding:55px; grid-template-columns:1fr; gap:45px; }.workflow-line { grid-template-columns:repeat(2,1fr); }.workflow-line::before { display:none; }.privacy-grid { max-width:none; }.source-section { grid-template-columns:66px minmax(0,1fr); }.source-action { grid-column:2; } }
@media (max-width:660px) { .landing-section,.landing-nav { width:min(100% - 30px,1180px); }.landing-nav { height:67px; }.landing-brand strong { font-size:13px; }.repo-entry { margin-left:auto; font-size:0; }.repo-entry svg { width:21px; height:21px; }.nav-entry { padding:9px 13px; font-size:11px; }.hero { padding:56px 0 65px; gap:42px; }.hero h1 { font-size:41px; }.hero-description { font-size:14px; }.hero-actions { align-items:stretch; flex-direction:column; }.hero-actions > * { width:100%; }.workflow-link { padding:8px; }.hero-promises { display:grid; gap:8px; }.preview-body { min-height:300px; grid-template-columns:42px 1fr; }.preview-sidebar { padding-inline:8px; }.preview-content { padding:15px 12px; }.preview-grid { grid-template-columns:1fr; }.stats-card { display:none; }.pipeline { grid-template-columns:repeat(4,1fr); }.pipeline > i,.pipeline small { display:none; }.pipeline > div { display:grid; justify-items:center; text-align:center; }.floating-note { display:none; }.trust-strip { padding:26px 18px; flex-direction:column; gap:11px; text-align:center; }.trust-strip i { display:none; }.features-section,.workflow-section { padding-block:85px; }.section-heading { margin-bottom:34px; }.feature-grid,.workflow-line,.privacy-grid { grid-template-columns:1fr; }.feature-card { min-height:320px; }.analysis-showcase,.privacy-section { width:100%; padding:65px 24px; border-radius:0; }.analysis-card { padding:20px; transform:none; }.workflow-line article { min-height:310px; }.privacy-grid article { min-height:auto; }.source-section { width:calc(100% - 30px); padding:34px 24px; grid-template-columns:1fr; justify-items:start; }.source-action { width:100%; min-width:0; grid-column:1; }.source-points { display:grid; gap:8px; }.final-cta { padding-block:95px; }.landing-footer { padding:35px 20px; grid-template-columns:1fr; text-align:center; justify-items:center; }.landing-footer > div { flex-wrap:wrap; justify-content:center; } }
</style>
