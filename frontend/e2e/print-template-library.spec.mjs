// 验证：设计器「选择模板」—— 模板库列表（带原图）+ 套用载入编辑器
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

// 「当前文件：xxx」行已删除
const hasCurFile = await page.evaluate(() => document.body.textContent.includes('当前文件'))
console.log('当前文件行已删除:', !hasCurFile ? 'PASS' : 'FAIL')

// 打开模板库
await page.click('.editor-bar button:has-text("选择模板")')
await page.waitForSelector('.lib-card', { timeout: 15000 })
await page.waitForTimeout(1200)   // 图片懒加载
const lib = await page.evaluate(() => ({
  groups: [...document.querySelectorAll('.lib-dir')].map((x) => x.textContent),
  cards: document.querySelectorAll('.lib-card').length,
  imgs: [...document.querySelectorAll('.lib-card img')].filter((i) => i.naturalWidth > 10).length,
}))
console.log('模板库:', JSON.stringify({ groups: lib.groups.length, cards: lib.cards, imgsLoaded: lib.imgs }))
await page.screenshot({ path: 'e2e/out-library.png' })

// 套用 五金行业 的 H356（编辑器内容应变化：A1 变成 XXX公司送货单）
await page.click('.lib-card:has-text("五金行业送货单H356")')
await page.waitForTimeout(600)
const mb = await page.evaluate(() => !!document.querySelector('.el-message-box'))
if (mb) await page.click('.el-message-box button.el-button--primary')   // 覆盖确认（编辑器打开时已载入，视为未脏? dirty=false 不弹）
await page.waitForTimeout(3000)
const a1 = await page.evaluate(() => window.luckysheet.getCellValue(0, 0))
const dirty = await page.evaluate(() => !!document.querySelector('.dirty-flag'))
console.log('套用后 A1:', JSON.stringify(a1), '| dirty:', dirty)
await page.screenshot({ path: 'e2e/out-library-applied.png' })
await browser.close()
console.log('DONE')
