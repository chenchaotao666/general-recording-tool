// 回归：单击打字 → Enter 提交 → 双击另一单元格（此前会 updatecell 崩溃）
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 150)))

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

// 1) 单击空白格 → 打字 → Enter
await page.mouse.click(grid.x + 400, grid.y + 500)
await page.waitForTimeout(300)
await page.keyboard.type('abc')
await page.waitForTimeout(200)
const typingBox = await page.evaluate(() => {
  const r = document.querySelector('#luckysheet-input-box').getBoundingClientRect()
  return { y: Math.round(r.y) }
})
await page.keyboard.press('Enter')
await page.waitForTimeout(600)
const boxAfterCommit = await page.evaluate(() => {
  const box = document.querySelector('#luckysheet-input-box')
  return { transform: box.style.transform || null, cssTop: getComputedStyle(box).top }
})
const committed = await page.evaluate(() => {
  const ls = window.luckysheet
  const range = ls.getRange()?.[0]
  const r = Math.max((range?.row?.[0] ?? 1) - 1, 0)
  return ls.getCellValue(r, range?.column?.[0] ?? 0)
})
console.log('typing box y:', typingBox.y, typingBox.y > 0 ? 'PASS(可见)' : 'FAIL(仍在屏外)')
console.log('committed value:', JSON.stringify(committed), committed === 'abc' ? 'PASS(已提交)' : 'FAIL')
console.log('after commit:', JSON.stringify(boxAfterCommit),
  boxAfterCommit.transform === null && parseInt(boxAfterCommit.cssTop) < 0 ? 'PASS(平移已清/top 保持停靠)' : 'FAIL')

// 2) 双击另一单元格 → 不应报 updatecell 错误，输入框正常出现
await page.mouse.dblclick(grid.x + 300, grid.y + 400)
await page.waitForTimeout(700)
const dbl = await page.evaluate(() => {
  const box = document.querySelector('#luckysheet-input-box')
  const r = box.getBoundingClientRect()
  return { y: Math.round(r.y), display: getComputedStyle(box).display,
           active: document.activeElement?.id }
})
console.log('dblclick box:', JSON.stringify(dbl), dbl.y > 0 && dbl.active === 'luckysheet-rich-text-editor' ? 'PASS' : 'FAIL')
console.log('pageerrors:', errors.length ? errors : '无')
await page.keyboard.press('Escape')
await browser.close()
console.log(errors.length === 0 && typingBox.y > 0 && dbl.y > 0 ? 'ALL PASS' : 'HAS FAIL')
