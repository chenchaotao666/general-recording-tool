// 画板 AI 生成（excalidraw）：描述 → LLM 产 nodes/edges → 画布渲染 → 自动保存落库
// 需要后端可达 LLM（本库已配 deepseek）；依赖外网代理
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
  headers, data: { title: 'E2E AI 生成', engine: 'excalidraw' },
})).json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => { localStorage.setItem('grt_token', t); localStorage.setItem('grt_user', JSON.stringify(u)) }, [token, user])
await page.goto(`${BASE}/whiteboard?wbId=${created.id}`)
await page.waitForSelector('.boot-overlay', { state: 'detached', timeout: 30000 }).catch(() => {})
await page.waitForSelector('.excalidraw', { timeout: 15000 })

// 打开 AI 生成对话框并生成
await page.click('button:has-text("AI 生成")')
await page.waitForSelector('.el-dialog textarea')
await page.fill('.el-dialog textarea', '请假审批流程：员工提交申请，主管审批，通过则人事备案后结束，驳回则退回员工修改重新提交')
await page.click('.el-dialog button:has-text("生成")')
// LLM 生成可能 10-60s
const genOk = await page.waitForSelector('.el-message--success', { timeout: 90000 }).then(() => 1).catch(() => 0)
results.push(['generate success toast', genOk])
await page.waitForTimeout(3000)   // onChange 防抖落库

const saved = await (await page.request.get(`${BASE}/api/whiteboards/${created.id}`, { headers })).json()
let elems = []
try { elems = JSON.parse(saved.content || '{}').elements || [] } catch { /* 空 */ }
const kinds = elems.reduce((m, e) => { m[e.type] = (m[e.type] || 0) + 1; return m }, {})
results.push(['elements total', elems.length])
results.push(['kinds', JSON.stringify(kinds)])
await page.screenshot({ path: 'e2e/out-ai-wb.png' })
await page.request.delete(`${BASE}/api/whiteboards/${created.id}`, { headers })
await browser.close()
results.forEach(([k, v]) => console.log(`${k}: ${v}`))
const ok = genOk === 1 && elems.length >= 6 && kinds.arrow >= 2 && !results.some(([k]) => k === 'pageerror')
console.log(ok ? 'PASS' : 'FAIL')
