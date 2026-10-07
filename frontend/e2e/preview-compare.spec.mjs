// 对比：打印入口预览（已保存模板） vs 编辑器预览（当前编辑器内容）
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

// 1) 打印入口预览（已保存模板）
await page.click('button:has-text("打印")')
await page.waitForSelector('.tpl-row')
await page.click('.tpl-row:has-text("H527") button:has-text("预览")')
await page.waitForSelector('.pv-frame', { timeout: 30000 })
await page.waitForTimeout(2000)
const outerEl = await page.$('.pv-frame')
await outerEl.screenshot({ path: 'e2e/out-preview-outer.png' })
await page.keyboard.press('Escape')
await page.waitForTimeout(400)
await page.click('.el-dialog button:has-text("关闭")').catch(() => {})
await page.waitForTimeout(400)

// 2) 编辑器预览
await page.click('button:has-text("打印")')
await page.waitForSelector('.tpl-row')
await page.click('.tpl-row:has-text("H527") button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)
await page.click('button:has-text("预览效果")')
await page.waitForSelector('.pv-frame', { timeout: 30000 })
await page.waitForTimeout(1500)
const innerEl = await page.$$('.pv-frame')
await innerEl[innerEl.length - 1].screenshot({ path: 'e2e/out-preview-designer.png' })
await browser.close()
console.log('DONE')
