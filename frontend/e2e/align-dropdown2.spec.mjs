// 点击居中单元格 → 打开对齐下拉 → 检查首次显示的选中项
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
await page.waitForSelector('.tpl-table tbody tr')
await page.click('.tpl-table tbody tr button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)

// 点 A1（合并标题，居中 ht=0）
const g = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
await page.mouse.click(g.x + 300, g.y + 30)
await page.waitForTimeout(500)

// 打开对齐下拉
await page.click('#luckysheet-icon-align')
await page.waitForTimeout(600)

const menu = await page.evaluate(() => {
  const menus = [...document.querySelectorAll('.luckysheet-cols-menu')].filter((m) => getComputedStyle(m).display !== 'none')
  return menus.map((m) => ({
    text: m.textContent.replace(/\s+/g, ' ').slice(0, 120),
    checked: [...m.querySelectorAll('.luckysheet-cols-menuitem-checked, .checked, [class*="check"]')].map((x) => x.textContent.trim()),
    items: [...m.querySelectorAll('.luckysheet-cols-menuitem')].map((x) => ({
      t: x.textContent.trim().slice(0, 12), cls: x.className.slice(0, 60),
    })),
  }))
})
console.log(JSON.stringify(menu, null, 1).slice(0, 1600))
await page.screenshot({ path: 'e2e/out-align-2.png' })
await browser.close()
