import { createRouter, createWebHistory } from 'vue-router'
import { api } from '../services/api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/auth/LoginView.vue'), meta: { title: '登录' } },
    { path: '/', name: 'overview', component: () => import('../views/dashboard/OverviewView.vue'), meta: { title: '工作台' } },
    { path: '/setup', name: 'setup', component: () => import('../views/setup/SetupView.vue'), meta: { title: '安装向导' } },
    { path: '/automation', name: 'automation', component: () => import('../views/automation/AutomationView.vue'), meta: { title: '自动投递' } },
    { path: '/jobs', name: 'jobs', component: () => import('../views/jobs/JobsView.vue'), meta: { title: '职位快照' } },
    { path: '/analysis', name: 'analysis', component: () => import('../views/analysis/AnalysisView.vue'), meta: { title: '职位分析' } },
    { path: '/profile', name: 'profile', component: () => import('../views/profile/ProfileView.vue'), meta: { title: '个人档案' } },
    { path: '/projects', name: 'projects', component: () => import('../views/library/ProjectsView.vue'), meta: { title: '项目库' } },
    { path: '/resumes', name: 'resumes', component: () => import('../views/library/ResumesView.vue'), meta: { title: '简历库' } },
    { path: '/templates', name: 'templates', component: () => import('../views/resume/TemplatesView.vue'), meta: { title: '简历模板' } },
    { path: '/rules', name: 'rules', component: () => import('../views/library/RulesView.vue'), meta: { title: '匹配规则' } },
    { path: '/models', name: 'models', component: () => import('../views/library/ModelsView.vue'), meta: { title: '模型配置' } },
    { path: '/admin/users', name: 'admin-users', component: () => import('../views/admin/AdminUsersView.vue'), meta: { title: '用户管理', adminOnly: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  if (to.name === 'login') return true
  try {
    const result = await api.me()
    if (to.meta.adminOnly && !result.user.isAdmin) return { name: 'overview' }
    return true
  } catch {
    return { name: 'login' }
  }
})

router.afterEach((route) => {
  document.title = `${String(route.meta.title || '工作台')} · Job Search Assistant`
})

export default router
