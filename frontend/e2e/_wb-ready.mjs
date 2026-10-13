// excalidraw 画板：加载遮罩 → 工具栏注入完成后撤罩；注入按钮存在；简单画一笔能保存
import { chromium } from 'playwright'
const BASE = 'http://localhost:5190'
const results = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('pageerror', (e) => results.push(['pageerror', String(e).slice(0, 160)]))
const login = await page.request.post(`${BASE}/api/auth/login`, { data: { username: 'admin', password: 'admin123' } })
const { token, user } = await login.json()
const headers = { Authorization: `Bearer ${token}` }
const created = await (await page.request.post(`${BASE}/api/whiteboards`, {
  headers, data: { title: 'E2E excal 遮罩', engine: 'excalidraw' },
})).json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => { localStorage.setItem('grt_token', t); localStorage.setItem('grt_user', JSON.stringify(u)) }, [token, user])
await page.goto(`${BASE}/whiteboard?wbId=${created.id}`)

// 遮罩应先出现（或不晚于工具栏出现前存在），随后消失
const overlayAppeared = await page.waitForSelector('.boot-overlay', { timeout: 5000 }).then(() => 1).catch(() => 0)
results.push(['overlay appeared', overlayAppeared])
await page.waitForSelector('.boot-overlay', { state: 'detached', timeout: 30000 })
results.push(['overlay gone', 1])
// 撤罩时注入的平铺按钮必须已经就位（顺序保证无闪动）
results.push(['injected tools', await page.locator('.wb-extra-tools .wb-extra-tool').count()])
// 画布可交互：拖一个矩形
const canvas = await page.$('.wb-excalidraw canvas')
const cb = await canvas.boundingBox()
await page.mouse.click(cb.x + 300, cb.y + 200)   // 聚焦画布
await page.keyboard.press('r')   // 矩形工具快捷键
await page.mouse.move(cb.x + 300, cb.y + 200)
await page.mouse.down(); await page.mouse.move(cb.x + 420, cb.y + 300, { steps: 6 }); await page.mouse.up()
await page.waitForTimeout(2500)
const saved = await (await page.request.get(`${BASE}/api/whiteboards/${created.id}`, { headers })).json()
results.push(['saved has elements', (JSON.parse(saved.content).elements || []).length])
await page.screenshot({ path: 'e2e/out-wb-ready.png' })
await page.request.delete(`${BASE}/api/whiteboards/${created.id}`, { headers })
await browser.close()
results.forEach(([k, v]) => console.log(`${k}: ${v}`))
const get = (k) => results.find(([x]) => x === k)?.[1]
const ok = get('overlay appeared') === 1 && get('overlay gone') === 1
  && get('injected tools') === 8 && get('saved has elements') >= 1
  && !results.some(([k]) => k === 'pageerror')
console.log(ok ? 'PASS' : 'FAIL')
