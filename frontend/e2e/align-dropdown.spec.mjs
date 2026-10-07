// 复现：点击居中单元格 → 工具栏对齐下拉首次打开显示状态不对
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

// A1 是合并的标题（居中）。点 A1
const g = await page.evaluate(() => { const r = document.querySelector("#ptSheetBox .luckysheet-grid-window").getBoundingClientRect(); return { x: r.x, y: r.y } })
  await page.mouse.click(g.x + 300, g.y + 30)
await page.waitForTimeout(500)
// 查 A1 的对齐属性
const cellInfo = await page.evaluate(() => {
  const d = window.luckysheet.getAllSheets()[0].data
  const c = d[0] && d[0][0]
  return { ht: c?.ht, vt: c?.vt }   // ht: 0 居中 1 左 2 右
})
console.log('A1 单元格属性:', JSON.stringify(cellInfo))

// 工具栏按钮当前状态（对齐按钮的图标/class）
const btnState = await page.evaluate(() => {
  const btn = document.querySelector('#luckysheet-icon-alignment-horizontal') ||
              document.querySelector('[data-tips*="水平"], [data-tips*="对齐"]')
  return btn ? { id: btn.id, cls: btn.className.slice(0, 80), html: btn.innerHTML.slice(0, 120) } : null
})
console.log('工具栏按钮:', JSON.stringify(btnState))
await page.screenshot({ path: 'e2e/out-align-1.png' })
await browser.close()
