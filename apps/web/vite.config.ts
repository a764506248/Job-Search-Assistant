import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // Local verification can point the UI at an isolated Docker API, while
    // keeping the existing 8765 default for normal development.
    proxy: {
      '/v1': process.env.JSA_WEB_API || 'http://127.0.0.1:8765',
      '/docs': process.env.JSA_WEB_API || 'http://127.0.0.1:8765',
      '/openapi.json': process.env.JSA_WEB_API || 'http://127.0.0.1:8765',
    },
  },
})
