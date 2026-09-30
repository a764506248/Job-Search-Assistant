import { defineConfig } from 'wxt'

export default defineConfig({
  modules: ['@wxt-dev/module-vue'],
  manifest: {
    name: 'Job Search Assistant - 简历图片测试版',
    version: '0.2.3',
    version_name: '0.2.3-resume-image-test',
    description: 'BOSS 直聘默认简历图片发送测试版（原职位采集功能已暂停）',
    permissions: ['storage'],
    host_permissions: ['https://www.zhipin.com/*', 'http://127.0.0.1/*'],
  },
})
