// 诊断：点击单元格后选区高亮/焦点是否可见
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

// 点击表格中部一个单元格
const grid = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
await page.mouse.click(grid.x + 400, grid.y + 300)
await page.waitForTimeout(600)

const sel = await page.evaluate(() => {
  const boxes = [...document.querySelectorAll('#ptSheetBox .luckysheet-cell-selected, #ptSheetBox .luckysheet-cell-selected-focus')]
    .map((el) => {
      const r = el.getBoundingClientRect()
      const cs = getComputedStyle(el)
      return {
        cls: el.className.slice(0, 50), display: cs.display, z: cs.zIndex,
        border: cs.border.slice(0, 60), bg: cs.background.slice(0, 60),
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      }
    })
  const inputBox = document.querySelector('#luckysheet-input-box, .luckysheet-input-box')
  return { boxes, inputBox: !!inputBox }
})
console.log(JSON.stringify(sel, null, 1))
await page.screenshot({ path: 'e2e/out-cell-focus.png' })
await browser.close()
console.log('DONE')
