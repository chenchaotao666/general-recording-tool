// 验证：设计器「预览效果」与打印入口共用同一对话框（纸张切换/打印按钮都在）
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e).slice(0, 150)))

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

await page.click('button:has-text("预览效果")')
await page.waitForSelector('.pv-frame', { timeout: 30000 })
await page.waitForTimeout(1200)
let info = await page.evaluate(() => {
  const doc = document.querySelector('.pv-frame')?.contentDocument
  return {
    title: [...document.querySelectorAll('.el-dialog__title')].map((x) => x.textContent).join(','),
    paperBtns: [...document.querySelectorAll('.el-radio-button')].map((x) => x.textContent.trim()),
    hasPrintBtn: !!document.querySelector('.el-dialog button.el-button--primary:not([disabled])'),
    hasRealData: /测试产品/.test(doc?.body?.textContent || ''),
    noTokens: !/\{items\.|\{_row\./.test(doc?.body?.textContent || ''),
  }
})
console.log('设计器预览:', JSON.stringify(info))
// 切到 2等分
await page.click('.el-radio-button:has-text("2等分")')
await page.waitForTimeout(1500)
info = await page.evaluate(() => ({
  pages: document.querySelector('.pv-frame')?.contentDocument?.querySelectorAll('.page').length ?? 0,
  halfCss: (document.querySelector('.pv-frame')?.contentDocument?.documentElement.textContent || '').includes('133mm'),
}))
console.log('2等分切换:', JSON.stringify(info))
await browser.close()
console.log('DONE')
