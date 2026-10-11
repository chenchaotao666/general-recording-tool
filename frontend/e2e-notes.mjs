/* 本轮实测：上移/置顶纯排序操作、格式刷刷子光标（普通/连续双色） */
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('pageerror', (e) => console.log('[pageerror]', e.message.slice(0, 300)))

await page.goto(BASE + '/login')
await page.fill('input[placeholder*="用户名"]', 'admin')
await page.fill('input[type="password"]', 'admin123')
await page.click('button.login-btn')
await page.waitForURL((u) => !u.pathname.includes('login'))
await page.goto(BASE + '/notes')
await page.waitForSelector('.notes-page')

// 建三页：甲、乙、丙（等目录行数增加再填标题，避免填到旧页面）
for (const t of ['甲', '乙', '丙']) {
  const cnt = await page.evaluate(() => document.querySelectorAll('.tree-item').length)
  await page.click('.side-top button')
  await page.waitForFunction((c) => document.querySelectorAll('.tree-item').length > c, cnt, { timeout: 10000 })
  await page.waitForSelector('[data-slate-editor]', { timeout: 15000 })
  await page.waitForTimeout(300)
  await page.fill('.title-input', `页面${t}`)
  await page.waitForTimeout(900)
}
const order = () => page.evaluate(() => [...document.querySelectorAll('.tree-title')].map((e) => e.textContent.trim()))

// 1. 上移：丙（最顶）下面的乙点「上移」→ 乙到丙前面
console.log('初始顺序:', JSON.stringify(await order()))
await page.hover('.tree-item:has-text("页面乙")')
await page.click('.tree-item:has-text("页面乙") .tree-ops .el-icon[title="上移"]')
await page.waitForTimeout(800)
let o = await order()
console.log('1. 乙上移一位:', o[0] === '页面乙' && o[1] === '页面丙' ? 'OK' : 'FAIL', JSON.stringify(o))

// 2. 置顶：甲（最后）点「置顶」→ 甲到最前
await page.hover('.tree-item:has-text("页面甲")')
await page.click('.tree-item:has-text("页面甲") .tree-ops .el-icon[title="置顶"]')
await page.waitForTimeout(800)
o = await order()
console.log('2. 甲置顶:', o[0] === '页面甲' ? 'OK' : 'FAIL', JSON.stringify(o))

// 3. 刷新后顺序保持（持久化）
await page.reload()
await page.waitForSelector('.notes-page')
await page.waitForTimeout(800)
o = await order()
console.log('3. 刷新后顺序保持:', o[0] === '页面甲' && o[1] === '页面乙' ? 'OK' : 'FAIL', JSON.stringify(o))

// 4. 格式刷光标：启用前 text，启用后刷子（data-uri svg），连续模式换色
await page.click('.tree-item:has-text("页面甲")')
await page.waitForSelector('[data-slate-editor]', { timeout: 15000 })
await page.click('.wang-editor-wrap [data-slate-editor]')
await page.keyboard.type('光标测试')
await page.waitForTimeout(600)
const cursorBefore = await page.evaluate(() => getComputedStyle(document.querySelector('[data-slate-editor]')).cursor)
await page.keyboard.press('Home')
await page.waitForTimeout(600)
await page.click('.re-toolbar button[data-tooltip="格式刷"]')
await page.waitForTimeout(300)
const cursorArmed = await page.evaluate(() => getComputedStyle(document.querySelector('[data-slate-editor]')).cursor)
console.log('4a. 格式刷单次模式光标:', cursorArmed.includes('data:image/svg') ? 'OK' : 'FAIL', '|', cursorArmed.slice(0, 60))
// 双击进连续模式
await page.click('.re-toolbar button[data-tooltip="格式刷"]')
await page.waitForTimeout(300)
const cursorLocked = await page.evaluate(() => getComputedStyle(document.querySelector('[data-slate-editor]')).cursor)
const lockedDiff = cursorLocked.includes('7c5cff') || (cursorLocked.includes('data:image/svg') && cursorLocked !== cursorArmed)
console.log('4b. 连续模式光标变色:', lockedDiff ? 'OK' : 'FAIL')
// Esc 退出，光标还原
await page.keyboard.press('Escape')
await page.waitForTimeout(300)
const cursorOff = await page.evaluate(() => getComputedStyle(document.querySelector('[data-slate-editor]')).cursor)
console.log('4c. Esc 后光标还原:', !cursorOff.includes('data:image/svg') ? 'OK' : 'FAIL', '|', cursorOff)

await browser.close()
console.log('\n实测完成 ✅')
process.exit(0)
