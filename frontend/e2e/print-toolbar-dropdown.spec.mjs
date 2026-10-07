// 验证：1) 工具栏下拉在对话框遮罩之上 2) 占位符芯片点击插入到选中单元格
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 300)))

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

// --- 1) 工具栏下拉 ---
const selects = await page.evaluate(() =>
  [...document.querySelectorAll('#ptSheetBox .luckysheet-toolbar-select')]
    .map((el) => el.id).filter(Boolean)
)
console.log('toolbar selects:', selects.slice(0, 6))
await page.click(`#${selects[0]}`)
await page.waitForTimeout(800)
const z = await page.evaluate(() => {
  const menu = [...document.querySelectorAll('.luckysheet-cols-menu')]
    .find((el) => getComputedStyle(el).display !== 'none')
  const overlayZ = getComputedStyle(document.querySelector('.el-overlay')).zIndex
  const r = menu?.getBoundingClientRect()
  return menu
    ? { menuZ: getComputedStyle(menu).zIndex, overlayZ, rect: { w: Math.round(r.width), h: Math.round(r.height) } }
    : { menuZ: null, overlayZ }
})
console.log('dropdown:', JSON.stringify(z), z.menuZ > z.overlayZ ? 'PASS(菜单在遮罩之上)' : 'FAIL')

// 选菜单第一项（改字体），确认菜单可交互
const clicked = await page.evaluate(() => {
  const menu = [...document.querySelectorAll('.luckysheet-cols-menu')]
    .find((el) => getComputedStyle(el).display !== 'none')
  const item = menu?.querySelector('.luckysheet-cols-menuitem')
  if (!item) return false
  item.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  return true
})
await page.waitForTimeout(500)
console.log('menu item clickable:', clicked)

// --- 2) 占位符芯片插入 ---
await page.click('.token-chip >> nth=0')   // 第一个「单据信息」字段
await page.waitForTimeout(500)
const cellVal = await page.evaluate(() => {
  const ls = window.luckysheet
  const range = ls.getRange()?.[0]
  return range ? ls.getCellValue(range.row[0], range.column[0]) : null
})
console.log('inserted cell value:', JSON.stringify(cellVal), /^\{.+\}$/.test(cellVal || '') ? 'PASS' : 'FAIL')

await page.screenshot({ path: 'e2e/out-print-designer.png', fullPage: false })
await browser.close()
console.log('DONE')
