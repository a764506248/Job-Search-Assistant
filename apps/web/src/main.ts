import { createApp } from 'vue'
import { Button, Checkbox, ConfigProvider, Input, Layout, Modal, Pagination } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import './styles/main.css'
import App from './app/App.vue'
import router from './router'
import { setUnauthorizedHandler } from './services/api'

// JWT 改造后新增：任何接口返回 401 都视为会话失效，直接回登录页。
setUnauthorizedHandler(() => {
  if (router.currentRoute.value.name !== 'login') router.replace({ name: 'login' })
})

createApp(App)
  .use(router)
  .use(Button)
  .use(Checkbox)
  .use(ConfigProvider)
  .use(Input)
  .use(Layout)
  .use(Modal)
  .use(Pagination)
  .mount('#app')
