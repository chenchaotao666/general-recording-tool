// 验证：模板列表改为带表头表格、无编号列、只剩 H527
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
await page.waitForSelector('.tpl-table', { timeout: 15000 })
await page.waitForTimeout(800)
const info = await page.evaluate(() => ({
  headers: [...document.querySelectorAll('.tpl-table th')].map((th) => th.textContent.trim()),
  hasCode: document.body.textContent.includes('A001') || document.body.textContent.includes('A004'),
  rows: [...document.querySelectorAll('.tpl-table tbody tr')].map((tr) => tr.textContent.replace(/\s+/g, ' ').slice(0, 60)),
}))
console.log(JSON.stringify(info, null, 1))
await page.screenshot({ path: 'e2e/out-picker-table.png' })
await browser.close()
console.log(info.headers.includes('模板名称') && info.headers.includes('操作') && !info.hasCode ? 'PASS' : 'CHECK')
