import { defineConfig } from 'wxt'

export default defineConfig({
  modules: ['@wxt-dev/module-vue'],
  manifest: {
    name: 'Job Search Assistant',
    version: '0.3.4',
    version_name: '0.3.4-boss-conversation-position',
    description: '连接本地 Job Search Assistant，安全执行 BOSS 职位读取与已确认动作',
    permissions: ['storage', 'tabs'],
    host_permissions: ['https://www.zhipin.com/*', 'http://127.0.0.1/*'],
  },
})
