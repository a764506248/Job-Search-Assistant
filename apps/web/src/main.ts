import { createApp } from 'vue'
import { Button, ConfigProvider, Layout, Modal } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import './styles/main.css'
import App from './app/App.vue'
import router from './router'

createApp(App)
  .use(router)
  .use(Button)
  .use(ConfigProvider)
  .use(Layout)
  .use(Modal)
  .mount('#app')
