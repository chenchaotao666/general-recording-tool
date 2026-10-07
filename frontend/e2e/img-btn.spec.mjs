// 找图片按钮（含「更多」菜单）+ getluckysheetfile 的图片写入测试
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
await page.waitForSelector('.tpl-table tbody tr')
await page.click('.tpl-table tbody tr button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)

// 打开「更多」菜单
const more = await page.evaluate(() => {
  const btn = [...document.querySelectorAll('#ptSheetBox [data-tips]')]
    .find((el) => /更多|more/i.test(el.getAttribute('data-tips') || ''))
  if (btn) { btn.click(); return { id: btn.id, tips: btn.getAttribute('data-tips') } }
  return null
})
console.log('更多按钮:', JSON.stringify(more))
await page.waitForTimeout(600)
// 展开后所有 data-tips
const all = await page.evaluate(() =>
  [...document.querySelectorAll('#ptSheetBox [data-tips], body > .luckysheet-cols-menu [data-tips], .luckysheetpopover [data-tips]')]
    .map((el) => ({ id: el.id, tips: el.getAttribute('data-tips') }))
    .filter((x) => /图|image|插入|insert/i.test(x.tips || '')))
console.log('图片/插入相关:', JSON.stringify(all))
await page.screenshot({ path: 'e2e/out-more-menu.png' })
await browser.close()
