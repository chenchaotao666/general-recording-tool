// 验证：库模板（items 语法）+ 平表 → 预览给友好错误而不是多份空白单据
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
await page.click('.lib-card:has-text("五金行业送货单H546")')
await page.waitForTimeout(600)
if (await page.evaluate(() => !!document.querySelector('.el-message-box'))) {
  await page.click('.el-message-box button.el-button--primary')
}
await page.waitForTimeout(3000)
await page.click('button:has-text("预览效果")')
await page.waitForTimeout(1500)
const msg = await page.evaluate(() =>
  [...document.querySelectorAll('.el-message')].map((m) => m.textContent).join(' | '))
console.log('提示:', JSON.stringify(msg))
await browser.close()
console.log(msg.includes('没有对应的子表') && msg.includes('_row') ? 'PASS' : 'FAIL')
