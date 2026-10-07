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
await page.click('.editor-bar button:has-text("选择模板")')
await page.waitForSelector('.lib-card', { timeout: 15000 })
await page.click('.lib-card:has-text("送货单格式H512")')
await page.waitForTimeout(600)
if (await page.evaluate(() => !!document.querySelector('.el-message-box'))) {
  await page.click('.el-message-box button.el-button--primary')
}
await page.waitForTimeout(3000)

const before = await page.evaluate(() => JSON.stringify((window.luckysheet.getAllSheets()[0].config || {}).rowlen))
console.log('before:', before)

const grid = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
// 明细行第2列（产品名称占位符格，约 grid.y+300）打字
await page.mouse.click(grid.x + 250, grid.y + 300)
await page.waitForTimeout(300)
await page.keyboard.type('{_row.product_name_with_long_text}', { delay: 20 })
await page.keyboard.press('Enter')
await page.waitForTimeout(600)

const after = await page.evaluate(() => JSON.stringify((window.luckysheet.getAllSheets()[0].config || {}).rowlen))
console.log('after :', after)
await browser.close()
