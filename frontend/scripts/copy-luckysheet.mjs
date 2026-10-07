// 把 luckysheet 的 dist 资源拷到 public/luckysheet（postinstall 自动执行）。
// luckysheet 以 script/css 全局方式加载，不走 vite 打包。
import { cpSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = join(root, 'node_modules', 'luckysheet', 'dist')
const dst = join(root, 'public', 'luckysheet')

mkdirSync(dst, { recursive: true })
for (const p of ['plugins', 'css', 'assets', 'fonts', 'expendPlugins', 'luckysheet.umd.js']) {
  cpSync(join(src, p), join(dst, p), { recursive: true })
}
console.log('[copy-luckysheet] ->', dst)
