// 验证：1) 重置为起始模板成功 2) 单元格直接点击输入 3) 芯片面板无内部滚动条
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 200)))

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

// --- 1) 重置为起始模板 ---
await page.click('button:has-text("重置为起始模板")')
await page.waitForTimeout(600)
const hasConfirm = await page.evaluate(() => {
  const b = document.querySelector('.el-message-box')
  return !!b && getComputedStyle(b).display !== 'none'
})
if (hasConfirm) {
  console.log('confirm shown (editor was dirty) -> 确认')
  await page.click('.el-message-box button.el-button--primary')
}
await page.waitForTimeout(5000)
const a1 = await page.evaluate(() => window.luckysheet.getCellValue(0, 0))
console.log('after reset A1:', JSON.stringify(a1), a1 ? 'PASS(已载入起始模板)' : 'FAIL')

// --- 2) 单元格直接输入：点击空白单元格 → 键盘输入 → Enter ---
const grid = await page.evaluate(() => {
  const el = document.querySelector('#ptSheetBox .luckysheet-grid-window')
  const r = (el || document.querySelector('#ptSheetBox')).getBoundingClientRect()
  return { x: r.x, y: r.y }
})
// 点一个靠下的空白单元格（约 J18 区域）
await page.mouse.click(grid.x + 420, grid.y + 420)
await page.waitForTimeout(400)
await page.keyboard.type('hello测试')
await page.waitForTimeout(300)
await page.keyboard.press('Enter')
await page.waitForTimeout(600)
const typed = await page.evaluate(() => {
  const ls = window.luckysheet
  const range = ls.getRange()?.[0]
  const r = Math.max((range?.row?.[0] ?? 1) - 1, 0)
  const c = range?.column?.[0] ?? 0
  return { row: r, col: c, value: ls.getCellValue(r, c) }
})
console.log('typed cell:', JSON.stringify(typed), typed.value === 'hello测试' ? 'PASS' : 'FAIL')

// --- 3) 芯片面板无内部滚动条 ---
const scroll = await page.evaluate(() =>
  [...document.querySelectorAll('.tg-chips')].map((el) => ({
    scrollable: el.scrollHeight > el.clientHeight + 1,
    h: el.clientHeight, sh: el.scrollHeight,
  }))
)
console.log('chips scroll check:', JSON.stringify(scroll), scroll.every((s) => !s.scrollable) ? 'PASS' : 'FAIL')

await page.screenshot({ path: 'e2e/out-reset-cellinput.png' })
await browser.close()
console.log('DONE')
