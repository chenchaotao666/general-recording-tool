// 画板 drawio 引擎冒烟：API 建 drawio 画板 → 页面打开 iframe 就绪 → 拖入图形触发自动保存 → 刷新验证内容落库
// 注意：embed.diagrams.net 需要走本机代理（127.0.0.1:7897）
import { chromium } from 'playwright'

const BASE = 'http://localhost:5190'
const results = []
const browser = await chromium.launch()
// 代理只给页面用，且绕过本机地址（API 请求直接打本地 vite）
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  proxy: { server: 'http://127.0.0.1:7897', bypass: 'localhost,127.0.0.1' },
  // diagrams.net 的 CDN 按 UA 拦截 HeadlessChrome（403），伪装成普通 Chrome
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36',
})
const page = await ctx.newPage()
page.on('pageerror', (e) => results.push(['pageerror', String(e).slice(0, 200)]))
page.on('console', (m) => { if (m.type() === 'error') console.log('[cerr]', m.text().slice(0, 140)) })

const login = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const { token, user } = await login.json()
const headers = { Authorization: `Bearer ${token}` }

// 1. API 创建 drawio 画板（验证后端引擎白名单）
const created = await (await page.request.post(`${BASE}/api/whiteboards`, {
  headers, data: { title: 'E2E drawio 画板', engine: 'drawio' },
})).json()
results.push(['created engine', created.engine])

await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => {
  localStorage.setItem('grt_token', t)
  localStorage.setItem('grt_user', JSON.stringify(u))
}, [token, user])

// 2. 打开画板页：树上有 drawio 徽标，iframe 就绪（以 drawio 内部画布容器出现为准，覆盖冷启动慢的情况）
await page.goto(`${BASE}/whiteboard?wbId=${created.id}`)
await page.waitForSelector('.engine-tag:has-text("drawio")')
results.push(['tree badge', 1])
let frameReady = false
for (let i = 0; i < 45 && !frameReady; i++) {
  await page.waitForTimeout(1000)
  const frame = page.frames().find((f) => f.url().includes('diagrams.net'))
  if (frame) {
    frameReady = await frame.evaluate(() => {
      const r = document.querySelector('.geDiagramContainer')?.getBoundingClientRect()
      return !!r && r.width > 10
    }).catch(() => false)
  }
}
results.push(['iframe ready', frameReady ? 1 : 0])

// 3. 从图形库拖一个矩形到画布中央 → autosave → 画板页 1s 防抖自动保存
if (results.find(([k]) => k === 'iframe ready')?.[1] === 1) {
  const frame = page.frames().find((f) => f.url().includes('embed.diagrams.net'))
  results.push(['drawio frame', frame ? 1 : 0])
  if (frame) {
    // 等侧边图形库出来，拖第一个图形到画布
    await frame.waitForSelector('.geSidebar', { timeout: 20000 }).catch(() => {})
    const shape = await frame.$('.geSidebar .geItem')
    const box = await frame.$('.geDiagramContainer')
    if (shape && box) {
      const sb = await shape.boundingBox()
      const cb = await box.boundingBox()
      await page.mouse.move(sb.x + sb.width / 2, sb.y + sb.height / 2)
      await page.mouse.down()
      await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2, { steps: 12 })
      await page.mouse.up()
      // autosave 500ms 回传 + 1s 防抖落库
      await page.waitForTimeout(3500)
    } else {
      results.push(['sidebar shape', 0])
    }
  }
}

// 4. 读库验证内容已保存（含 mxfile XML 且非空）
const saved = await (await page.request.get(`${BASE}/api/whiteboards/${created.id}`, { headers })).json()
let savedXml = ''
try { savedXml = JSON.parse(saved.content || '{}').xml || '' } catch { /* 非预期格式 */ }
results.push(['saved has xml', savedXml.includes('<mxfile') ? 1 : 0])
results.push(['saved xml len', savedXml.length])
await page.screenshot({ path: 'e2e/out-drawio.png' })

// 5. 清理
await page.request.delete(`${BASE}/api/whiteboards/${created.id}`, { headers })

await browser.close()
results.forEach(([k, v]) => console.log(`${k}: ${v}`))
const get = (k) => results.find(([x]) => x === k)?.[1]
const ok = get('created engine') === 'drawio'
  && get('tree badge') === 1 && get('iframe ready') === 1
  && get('saved has xml') === 1
  && !results.some(([k]) => k === 'pageerror')
console.log(ok ? 'PASS' : 'FAIL')
