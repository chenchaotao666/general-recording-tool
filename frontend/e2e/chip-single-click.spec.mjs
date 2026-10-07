// 矩阵：单击+芯片 / 单击+打字 / 双击+芯片(光标处) / 双击+打字
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 120)))

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
const boxState = () => page.evaluate(() => {
  const b = document.querySelector('#luckysheet-input-box')
  return { top: getComputedStyle(b).top, text: b.textContent }
})
const curVal = () => page.evaluate(() => {
  const ls = window.luckysheet
  const r = ls.getRange()?.[0]
  return r ? ls.getCellValue(r.row[0], r.column[0]) : null
})

// 1) 单击选格 + 点芯片
await page.mouse.click(grid.x + 480, grid.y + 500)
await page.waitForTimeout(300)
await page.click('.token-group:nth-of-type(1) .token-chip:text-is("交货日期")')
await page.waitForTimeout(400)
let v = await curVal()
console.log('1 单击+芯片:', JSON.stringify(v), v === '{delivery_date}' ? 'PASS' : 'FAIL')

// 2) 单击选格 + 打字（焦点可能在停靠编辑器上）
await page.mouse.click(grid.x + 550, grid.y + 600)
await page.waitForTimeout(300)
await page.keyboard.type('xy', { delay: 50 })
await page.waitForTimeout(300)
let st = await boxState()
console.log('2 单击+打字:', JSON.stringify(st), parseInt(st.top) > 0 && st.text === 'xy' ? 'PASS' : 'FAIL')
await page.keyboard.press('Escape')
await page.waitForTimeout(300)

// 3) 双击进编辑 + 点芯片（光标处插入，原文保留）
await page.mouse.dblclick(grid.x + 350, grid.y + 400)
await page.waitForTimeout(500)
await page.keyboard.type('NO:', { delay: 40 })
await page.click('.token-group:nth-of-type(1) .token-chip:text-is("交货日期")')
await page.waitForTimeout(400)
st = await boxState()
console.log('3 双击+芯片:', JSON.stringify(st), st.text === 'NO:{delivery_date}' ? 'PASS' : 'FAIL')
await page.keyboard.press('Escape')
await page.waitForTimeout(300)

// 4) 双击 + 打字（原位编辑）
await page.mouse.dblclick(grid.x + 600, grid.y + 300)
await page.waitForTimeout(400)
await page.keyboard.type('zz', { delay: 50 })
st = await boxState()
console.log('4 双击+打字:', JSON.stringify(st), parseInt(st.top) > 0 && st.text.includes('zz') ? 'PASS' : 'FAIL')
await page.keyboard.press('Escape')

console.log('pageerrors:', errors.length ? errors : '无')
await browser.close()
