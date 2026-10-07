// 诊断：单击选格后打字，输入框的位置/可见性
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

const grid = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
await page.mouse.click(grid.x + 400, grid.y + 300)
await page.waitForTimeout(400)
await page.keyboard.type('测')
await page.waitForTimeout(600)

const info = await page.evaluate(() => {
  const out = []
  for (const sel of ['#luckysheet-input-box', '.luckysheet-input-box', '.luckysheet-rich-text-editor']) {
    for (const el of document.querySelectorAll(sel)) {
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      out.push({
        sel, display: cs.display, visibility: cs.visibility, opacity: cs.opacity, z: cs.zIndex,
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        text: (el.textContent || el.value || '').slice(0, 20),
        parents: (() => { let p = el, s = []; for (let i = 0; i < 4 && p; i++, p = p.parentElement) s.push(p.id || p.className?.slice?.(0, 30)); return s.join(' < ') })(),
      })
    }
  }
  return { out, active: document.activeElement?.id || document.activeElement?.className?.slice?.(0, 40) }
})
console.log(JSON.stringify(info, null, 1))
await page.screenshot({ path: 'e2e/out-typing2.png' })
await browser.close()
console.log('DONE')
