// 验证：模板库卡片图片点击 = 放大预览（不套用模板）
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const login = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const { token, user } = await login.json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => {
  localStorage.setItem('grt_token', t)
  localStorage.setItem('grt_user', JSON.stringify(u))
}, [token, user])
await page.goto(`${BASE}/t/35`)
await page.waitForSelector('button:has-text("打印")')
await page.click('button:has-text("打印")')
await page.waitForSelector('.tpl-row')
await page.click('.tpl-row:has-text("H527") button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)
const before = await page.evaluate(() => window.luckysheet.getCellValue(0, 0))

await page.click('.editor-bar button:has-text("选择模板")')
await page.waitForSelector('.lib-card .lib-img img', { timeout: 15000 })
await page.waitForTimeout(1000)
// 点图片 → 应打开大图预览而不是套用
await page.click('.lib-card .lib-img img >> nth=0')
await page.waitForTimeout(800)
const viewer = await page.evaluate(() => !!document.querySelector('.el-image-viewer__wrapper'))
const after = await page.evaluate(() => window.luckysheet.getCellValue(0, 0))
console.log('大图预览打开:', viewer ? 'PASS' : 'FAIL', '| 编辑器内容未变:', before === after ? 'PASS' : 'FAIL')
await page.screenshot({ path: 'e2e/out-lib-imgviewer.png' })
await browser.close()
