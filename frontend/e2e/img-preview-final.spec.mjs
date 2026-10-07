// 预览已保存的带图模板
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
await page.click('button:has-text("打印") >> nth=0')
await page.waitForSelector('.tpl-table tbody tr')
await page.click('.tpl-table tbody tr:has-text("cccc") button:has-text("预览")')
await page.waitForSelector('.pv-frame', { timeout: 30000 })
await page.waitForTimeout(1500)
const imgShown = await page.evaluate(() => {
  const f = document.querySelector('.pv-frame')
  const imgs = f?.contentDocument?.querySelectorAll('.page img')
  return { count: imgs?.length ?? 0, w: imgs?.[0]?.getBoundingClientRect().width }
})
console.log('预览图片:', JSON.stringify(imgShown))
await page.screenshot({ path: 'e2e/out-img-preview.png' })
await browser.close()
console.log(imgShown.count > 0 ? 'PASS' : 'FAIL')
