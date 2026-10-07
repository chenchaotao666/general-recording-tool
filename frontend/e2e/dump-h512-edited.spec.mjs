// 套用 H512 → 删除序号列 → 改 A7 占位符 → 抓 JSON（复现用户编辑）
import { chromium } from 'playwright'
import { writeFileSync } from 'node:fs'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e).slice(0, 150)))

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
await page.click('.editor-bar button:has-text("选择模板")')
await page.waitForSelector('.lib-card', { timeout: 15000 })
await page.click('.lib-card:has-text("送货单格式H512")')
await page.waitForTimeout(600)
if (await page.evaluate(() => !!document.querySelector('.el-message-box'))) {
  await page.click('.el-message-box button.el-button--primary')
}
await page.waitForTimeout(3000)

await page.evaluate(() => window.luckysheet.deleteColumn(0, 0))
await page.waitForTimeout(500)
await page.evaluate(() => window.luckysheet.setCellValue(6, 0, '{_row.product_name}'))
await page.waitForTimeout(500)

const sheets = await page.evaluate(() => window.luckysheet.getAllSheets())
writeFileSync('e2e/out-sheets-h512-edited.json', JSON.stringify(sheets))
console.log('saved')
await browser.close()
