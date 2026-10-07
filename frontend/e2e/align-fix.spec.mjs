import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e).slice(0, 120)))

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

const g = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})

async function checkMenu(cx, cy, label) {
  await page.mouse.click(g.x + cx, g.y + cy)
  await page.waitForTimeout(400)
  const btnType = await page.evaluate(() => document.querySelector('#luckysheet-icon-align')?.getAttribute('type'))
  await page.evaluate(() => document.querySelector('#luckysheet-icon-align-menu').click())
  await page.waitForTimeout(500)
  const res = await page.evaluate(() => {
    const menu = document.getElementById('luckysheet-icon-align-menu-menuButton')
    if (!menu) return null
    const items = [...menu.querySelectorAll('.luckysheet-cols-menuitem')]
    const checked = items.find((it) => it.querySelector('span.icon i.fa-check'))
    return { checked: checked?.getAttribute('itemvalue') ?? '(none)' }
  })
  console.log(label, '| 按钮type:', btnType, '| 下拉勾选:', res?.checked,
    btnType === res?.checked ? 'PASS' : 'FAIL')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
}

await checkMenu(300, 30, 'A1(居中)')
await checkMenu(300, 130, '信息区(左对齐)')
await checkMenu(300, 30, 'A1(居中)-重开')
await browser.close()
