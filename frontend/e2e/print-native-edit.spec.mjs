// 全链路验证：打字→Enter→再打字→点他格提交→中文→双击带内容→保存 JSON 导出校验
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 120)))

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

const grid = await page.evaluate(() => {
  const r = document.querySelector('#ptSheetBox .luckysheet-grid-window').getBoundingClientRect()
  return { x: r.x, y: r.y }
})
const boxState = () => page.evaluate(() => {
  const b = document.querySelector('#luckysheet-input-box')
  return { top: getComputedStyle(b).top, text: b.textContent,
           y: Math.round(b.getBoundingClientRect().y), active: document.activeElement?.id }
})

// 1) 单击打字 → 原生编辑框带出 abc
await page.mouse.click(grid.x + 350, grid.y + 400)
await page.waitForTimeout(300)
await page.keyboard.type('abc', { delay: 50 })
await page.waitForTimeout(300)
let st = await boxState()
console.log('1 打字:', JSON.stringify(st), st.y > 0 && st.text === 'abc' ? 'PASS' : 'FAIL')

// 2) Enter 提交（假编辑状态）→ 立刻再打字 → 应在新选区开编辑
await page.keyboard.press('Enter')
await page.waitForTimeout(500)
await page.keyboard.type('de', { delay: 50 })
await page.waitForTimeout(300)
st = await boxState()
console.log('2 Enter后再打字:', JSON.stringify(st), st.y > 0 && st.text === 'de' ? 'PASS' : 'FAIL')

// 3) 编辑中点另一格 → de 提交、编辑框停靠
const sel2 = await page.evaluate(() => window.luckysheet.getRange()?.[0])
await page.mouse.click(grid.x + 550, grid.y + 300)
await page.waitForTimeout(500)
const committed = await page.evaluate(([r, c]) => window.luckysheet.getCellValue(r, c), [sel2.row[0], sel2.column[0]])
st = await boxState()
console.log('3 点他格提交:', JSON.stringify({ committed, top: st.top }),
  committed === 'de' && parseInt(st.top) < 0 ? 'PASS' : 'FAIL')

// 4) 中文（IME 提交）
await page.keyboard.insertText('中文测试')
await page.waitForTimeout(500)
st = await boxState()
console.log('4 中文:', JSON.stringify(st), st.text === '中文测试' && st.y > 0 ? 'PASS' : 'FAIL')
await page.keyboard.press('Enter')
await page.waitForTimeout(500)

// 5) 双击带内容的格子 → 编辑器带出原内容
await page.mouse.dblclick(grid.x + 350, grid.y + 400)
await page.waitForTimeout(600)
st = await boxState()
console.log('5 双击带内容:', JSON.stringify(st), st.text === 'abc' && st.y > 0 ? 'PASS' : 'FAIL')
await page.keyboard.press('Escape')
await page.waitForTimeout(300)

console.log('pageerrors:', errors.length ? errors : '无')
await page.screenshot({ path: 'e2e/out-native-final.png' })
await browser.close()
console.log(errors.length === 0 ? 'DONE' : 'HAS ERRORS')
