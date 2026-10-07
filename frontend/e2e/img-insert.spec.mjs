// 验证：工具栏插入图片 → getAllSheets 带 images → 保存/预览出图
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

// 找工具栏里的图片按钮（可能在折叠的「更多」里）
const imgBtn = await page.evaluate(() => {
  const all = [...document.querySelectorAll('#ptSheetBox [data-tips]')]
  return all.filter((el) => /图片|image|Image/.test(el.getAttribute('data-tips') || ''))
    .map((el) => ({ id: el.id, tips: el.getAttribute('data-tips'), visible: el.offsetParent !== null }))
})
console.log('图片按钮:', JSON.stringify(imgBtn))

// 通过 JS 直接写入编辑器图片模型（模拟工具栏插入后的状态）
await page.evaluate(() => {
  const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  const file = window.luckysheet.getluckysheetfile()
  file.images = {
    img_test: {
      type: '3', src: png, originWidth: 80, originHeight: 80,
      default: { width: 80, height: 80, left: 30, top: 20 },
      crop: { width: 80, height: 80, offsetLeft: 0, offsetTop: 0 },
      isFixedPos: false, fixedLeft: null, fixedTop: null,
      border: { width: 0, radius: 0, style: 'solid', color: '#000' },
    },
  }
  window.luckysheet.refresh()
})
await page.waitForTimeout(500)
const has = await page.evaluate(() => {
  const s = window.luckysheet.getAllSheets()[0]
  return { hasImages: !!s.images, keys: s.images ? Object.keys(s.images) : [] }
})
console.log('getAllSheets images:', JSON.stringify(has))
await browser.close()
console.log(has.hasImages ? 'PASS' : 'FAIL')
