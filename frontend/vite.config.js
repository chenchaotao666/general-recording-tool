import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const __BUILD_TIME__ = new Date().toLocaleString('zh-CN', { hour12: false })

export default defineConfig({
  define: {
    __BUILD_TIME__: JSON.stringify(__BUILD_TIME__),
  },
  plugins: [vue()],
  server: {
    port: 5173,
    // 代理目标可用 VITE_API_TARGET 覆盖（本地并行起第二个后端联调时用）
    proxy: { '/api': process.env.VITE_API_TARGET || 'http://localhost:8000' },
  },
  // vitest 只收 tests/ 下的单元测试；e2e/ 是 Playwright 真实浏览器测试，不走 vitest
  test: {
    include: ['tests/**/*.test.js'],
  },
})
