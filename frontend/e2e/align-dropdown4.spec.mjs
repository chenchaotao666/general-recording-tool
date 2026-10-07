// 隐藏左侧面板 → 工具栏展开 → 测对齐下拉首次选中项
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
await page.waitForSelector('.tpl-table tbody tr')
await page.click('.tpl-table tbody tr button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)
// 隐藏左侧面板，给工具栏腾宽度
await page.evaluate(() => { document.querySelector('.pt-designer .cfg').style.display = 'none' })
await page.waitForTimeout(800)

const g = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
await page.mouse.click(g.x + 300, g.y + 30)   // A1 居中
await page.waitForTimeout(500)
const btn = await page.evaluate(() => document.querySelector('#luckysheet-icon-align')?.getAttribute('type'))
console.log('对齐按钮 type =', btn)
await page.click('#luckysheet-icon-align')
await page.waitForTimeout(600)
const menu = await page.evaluate(() => {
  const m = [...document.querySelectorAll('.luckysheet-cols-menu')].find((x) => getComputedStyle(x).display !== 'none')
  if (!m) return null
  return {
    items: [...m.querySelectorAll('.luckysheet-cols-menuitem')].map((x) => ({
      t: x.textContent.trim().slice(0, 10),
      cls: x.className,
      checked: x.querySelector('.luckysheet-iconfont-check') !== null || x.className.includes('checked'),
    })),
    rawHtml: m.innerHTML.slice(0, 600),
  }
})
console.log('菜单:', JSON.stringify(menu?.items ?? menu?.rawHtml, null, 1).slice(0, 1200))
await page.screenshot({ path: 'e2e/out-align-3.png' })
await browser.close()
