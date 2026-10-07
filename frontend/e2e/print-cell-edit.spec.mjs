// 诊断：双击单元格进入编辑时，输入框（caret）是否出现、位置是否正确
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

const grid = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
const cx = grid.x + 400, cy = grid.y + 300

// 双击进入编辑
await page.mouse.dblclick(cx, cy)
await page.waitForTimeout(600)
const dbl = await page.evaluate(() => {
  const box = document.querySelector('#luckysheet-input-box')
  if (!box) return { box: false }
  const r = box.getBoundingClientRect()
  const cs = getComputedStyle(box)
  return {
    box: true, display: cs.display, z: cs.zIndex,
    rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    active: document.activeElement?.id || document.activeElement?.className?.slice?.(0, 40),
  }
})
console.log('after dblclick input box:', JSON.stringify(dbl))
await page.screenshot({ path: 'e2e/out-dblclick.png' })

// 不保存直接 Esc 退出编辑
await page.keyboard.press('Escape')
await page.waitForTimeout(300)

// 单击后按 F2/或直接打字时的输入框
await page.mouse.click(cx, cy)
await page.waitForTimeout(300)
await page.keyboard.type('X')
await page.waitForTimeout(400)
const typing = await page.evaluate(() => {
  const box = document.querySelector('#luckysheet-input-box')
  if (!box) return { box: false }
  const r = box.getBoundingClientRect()
  const cs = getComputedStyle(box)
  return { display: cs.display, z: cs.zIndex, rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } }
})
console.log('while typing input box:', JSON.stringify(typing))
await page.screenshot({ path: 'e2e/out-typing.png' })
await page.keyboard.press('Escape')
await browser.close()
console.log('DONE')
