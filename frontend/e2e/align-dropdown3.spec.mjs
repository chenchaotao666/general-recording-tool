// 点击居中单元格 → JS 打开对齐下拉 → 检查首次显示的选中项
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

const g = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})

async function checkAlign(cx, cy, label) {
  await page.mouse.click(g.x + cx, g.y + cy)
  await page.waitForTimeout(400)
  const btn = await page.evaluate(() => document.querySelector('#luckysheet-icon-align')?.getAttribute('type'))
  await page.evaluate(() => document.querySelector('#luckysheet-icon-align').click())
  await page.waitForTimeout(500)
  const menu = await page.evaluate(() => {
    const m = [...document.querySelectorAll('.luckysheet-cols-menu')].find((x) => getComputedStyle(x).display !== 'none')
    if (!m) return null
    return {
      text: m.textContent.replace(/\s+/g, ' ').slice(0, 100),
      checkedItems: [...m.querySelectorAll('.luckysheet-cols-menuitem')].map((x) => ({
        t: x.textContent.trim().slice(0, 10),
        checked: x.className.includes('checked') || !!x.querySelector('[class*="check"]:not([style*="none"])'),
        html: x.innerHTML.slice(0, 80),
      })),
    }
  })
  console.log(label, '| 按钮 type =', btn, '| 菜单:', JSON.stringify(menu?.checkedItems ?? menu?.text))
  // 关闭菜单
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
}

await checkAlign(300, 30, 'A1(居中ht=0)')
await checkAlign(400, 130, '信息区(左对齐ht=1)')
await browser.close()
