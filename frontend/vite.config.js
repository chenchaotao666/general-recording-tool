import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  // vitest 只收 tests/ 下的单元测试；e2e/ 是 Playwright 真实浏览器测试，不走 vitest
  test: {
    include: ['tests/**/*.test.js'],
  },
})
