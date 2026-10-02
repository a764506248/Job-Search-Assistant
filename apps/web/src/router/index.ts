import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('../views/dashboard/OverviewView.vue'), meta: { title: '工作台' } },
    { path: '/setup', name: 'setup', component: () => import('../views/setup/SetupView.vue'), meta: { title: '安装向导' } },
    { path: '/jobs', name: 'jobs', component: () => import('../views/jobs/JobsView.vue'), meta: { title: '职位快照' } },
    { path: '/profile', name: 'profile', component: () => import('../views/profile/ProfileView.vue'), meta: { title: '个人档案' } },
    { path: '/projects', name: 'projects', component: () => import('../views/library/ProjectsView.vue'), meta: { title: '项目库' } },
    { path: '/resumes', name: 'resumes', component: () => import('../views/library/ResumesView.vue'), meta: { title: '简历库' } },
    { path: '/templates', name: 'templates', component: () => import('../views/resume/TemplatesView.vue'), meta: { title: '简历模板' } },
    { path: '/rules', name: 'rules', component: () => import('../views/library/RulesView.vue'), meta: { title: '匹配规则' } },
    { path: '/models', name: 'models', component: () => import('../views/library/ModelsView.vue'), meta: { title: '模型配置' } },
    { path: '/knowledge', name: 'knowledge', component: () => import('../views/knowledge/KnowledgeView.vue'), meta: { title: '向量知识库' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((route) => {
  document.title = `${String(route.meta.title || '工作台')} · Job Search Assistant`
})

export default router
