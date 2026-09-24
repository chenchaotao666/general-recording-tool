// 真实 App 复现：登录 → 记事本 → 建页 → 输标题 → 逐字删 → 退格回上一行，逐步 dump DOM+数据
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const results = []
const browser = await chromium.launch()
const page = await browser.newPage()

// 登录拿 token
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

async function dump(label) {
  const d = await page.evaluate(() => {
    const dom = [...document.querySelectorAll('.ce-block')].map((b) => ({
      tag: b.querySelector('[contenteditable]')?.tagName || '(none)',
      text: b.textContent.slice(0, 24),
      cls: b.querySelector('[contenteditable]')?.className || '',
    }))
    return {
      dom,
      activeTag: document.activeElement?.tagName,
      title: document.querySelector('.title-input')?.value,
    }
  })
  results.push({ label, ...d })
  return d
}

// 新建页面 → 输入两行：第一段 + "# " 转标题
await page.click('.side-top .el-button--primary')
await page.waitForSelector('.editor-holder .ce-paragraph')
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.type('第一段普通文字')
await page.keyboard.press('Enter')
await page.keyboard.type('#')
await page.keyboard.press(' ')
await page.waitForTimeout(200)
await page.keyboard.type('标题行内容')
await page.waitForTimeout(200)
await dump('A0: 输入完成')

// 逐字删除标题（5 字）+ 退格回上一行
for (let i = 1; i <= 6; i++) {
  await page.keyboard.press('Backspace')
  await page.waitForTimeout(150)
  await dump(`A${i}: Backspace x${i}`)
}

console.log(JSON.stringify(results, null, 2))
await browser.close()
