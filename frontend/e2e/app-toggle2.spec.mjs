// 验证折叠块：Enter 不跳出、内容区换行、空折叠块可 Backspace 删除
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const results = []
const browser = await chromium.launch()
const page = await browser.newPage()

const login = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const { token, user } = await login.json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => {
  localStorage.setItem('grt_token', t)
  localStorage.setItem('grt_user', JSON.stringify(u))
}, [token, user])
await page.goto(`${BASE}/notes`)
await page.waitForSelector('.notes-page')

await page.click('.side-top .el-button--primary')
await page.waitForSelector('.editor-holder .ce-paragraph')
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.type('>')
await page.keyboard.press(' ')
await page.waitForTimeout(300)
await page.keyboard.type('标题')

async function dump(label) {
  const d = await page.evaluate(() => {
    const t = document.querySelector('.toggle-block')
    return {
      hasToggle: !!t,
      activeCls: document.activeElement?.className || document.activeElement?.tagName,
      bodyText: document.querySelector('.toggle-body')?.innerHTML,
      blockCount: document.querySelectorAll('.ce-block').length,
      blockTypes: [...document.querySelectorAll('.ce-block')].map((b) => b.querySelector('[contenteditable]')?.className?.split(' ')[0]),
    }
  })
  results.push({ label, ...d })
}

// 1. 标题里按 Enter → 应进入内容区，不新建块
await page.keyboard.press('Enter')
await page.waitForTimeout(200)
await dump('T1: 标题里Enter')

// 2. 内容区输入 + Enter 换行
await page.keyboard.type('第一行')
await page.keyboard.press('Enter')
await page.keyboard.type('第二行')
await page.waitForTimeout(200)
await dump('T2: 内容区Enter换行')

// 3. 删空整个折叠块（全选标题+内容删除后 Backspace）
await page.evaluate(() => {
  const t = document.querySelector('.toggle-title')
  const b = document.querySelector('.toggle-body')
  t.innerHTML = ''
  b.innerHTML = ''
  b.focus()
})
await page.keyboard.press('Backspace')
await page.waitForTimeout(300)
await dump('T3: 空折叠块Backspace')

console.log(JSON.stringify(results, null, 2))
await browser.close()
