import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e).slice(0, 120)))

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
const grid = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
await page.mouse.dblclick(grid.x + 350, grid.y + 400)
await page.waitForTimeout(500)
await page.keyboard.type('单号:', { delay: 40 })
await page.waitForTimeout(200)
await page.click('.token-group:nth-of-type(1) .token-chip:text-is("单号")')
await page.waitForTimeout(500)
const st = await page.evaluate(() => ({
  text: document.querySelector('#luckysheet-input-box').textContent,
  active: document.activeElement?.id,
}))
console.log('编辑中点芯片:', JSON.stringify(st),
  st.text === '单号:{order_no}' && st.active === 'luckysheet-rich-text-editor' ? 'PASS' : 'FAIL')
await page.waitForTimeout(300)
await page.click('button:has-text("重置为起始模板")')
await page.waitForTimeout(600)
if (await page.evaluate(() => !!document.querySelector('.el-message-box'))) {
  await page.click('.el-message-box button.el-button--primary')
}
await page.waitForTimeout(5000)
await page.screenshot({ path: 'e2e/out-starter.png' })
await browser.close()
console.log('DONE')
