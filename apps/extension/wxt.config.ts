import { defineConfig } from 'wxt'

export default defineConfig({
  modules: ['@wxt-dev/module-vue'],
  manifest: {
    name: 'Job Search Assistant',
    description: '基于本地知识库的 Boss 直聘求职辅助工具',
    permissions: ['storage'],
    host_permissions: ['https://www.zhipin.com/*', 'http://127.0.0.1/*'],
    web_accessible_resources: [
      {
        resources: ['boss.js'],
        matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
      },
    ],
  },
})
