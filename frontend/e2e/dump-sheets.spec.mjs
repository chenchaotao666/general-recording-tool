// 抓取编辑器里 H527 模板的 getAllSheets JSON 供离线对比
import { chromium } from 'playwright'
import { writeFileSync } from 'node:fs'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage()
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
const sheets = await page.evaluate(() => window.luckysheet.getAllSheets())
writeFileSync('e2e/out-sheets-h527.json', JSON.stringify(sheets))
console.log('saved', JSON.stringify(sheets).length, 'bytes')
await browser.close()
