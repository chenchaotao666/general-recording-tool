// 套用库模板 H512 后抓取编辑器 JSON，分析行高来源
import { chromium } from 'playwright'
import { writeFileSync } from 'node:fs'

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
await page.click('.editor-bar button:has-text("选择模板")')
await page.waitForSelector('.lib-card', { timeout: 15000 })
await page.click('.lib-card:has-text("送货单格式H512")')
await page.waitForTimeout(600)
if (await page.evaluate(() => !!document.querySelector('.el-message-box'))) {
  await page.click('.el-message-box button.el-button--primary')
}
await page.waitForTimeout(3000)
// 编辑器里实际渲染的行高 vs JSON rowlen
const info = await page.evaluate(() => {
  const sheets = window.luckysheet.getAllSheets()
  const cfg = sheets[0].config || {}
  // 实际 DOM 行高：找前两行单元格
  const rows = [...document.querySelectorAll('#ptSheetBox .luckysheet-cell-main tr')].slice(0, 10)
    .map((tr) => Math.round(tr.getBoundingClientRect().height))
  return { rowlen: cfg.rowlen || null, domRows: rows }
})
console.log(JSON.stringify(info, null, 1))
writeFileSync('e2e/out-sheets-h512.json', JSON.stringify(await page.evaluate(() => window.luckysheet.getAllSheets())))
await browser.close()
