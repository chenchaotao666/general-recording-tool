// 验证：空块空格 → AI 面板开关/错误路径；空块 / → 块命令菜单
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

async function state(label) {
  const d = await page.evaluate(() => ({
    aiPanel: !!document.querySelector('.ai-panel'),
    aiError: document.querySelector('.ai-error')?.textContent || '',
    toolbox: !!document.querySelector('.ce-toolbox--opened, .ce-toolbox.opened, [class*=toolbox][class*=opened]'),
    blocks: [...document.querySelectorAll('.ce-block')].map((b) => b.querySelector('[contenteditable]')?.tagName),
  }))
  results.push({ label, ...d })
  return d
}

// 新建页面
await page.click('.side-top .el-button--primary')
await page.waitForSelector('.editor-holder .ce-paragraph')
await page.click('.editor-holder .ce-paragraph')

// 1. 空块按空格 → AI 面板出现
await page.keyboard.press(' ')
await page.waitForTimeout(300)
await state('S1: 空块空格后')

// 2. 输入指令 + Enter → 走错误路径（测试库未配置模型）但面板流程正确
await page.keyboard.type('写一份周报')
await page.keyboard.press('Enter')
await page.waitForTimeout(2000)
await state('S2: 生成（无模型配置）')

// 3. Esc 关闭面板
await page.keyboard.press('Escape')
await page.waitForTimeout(300)
await state('S3: Esc 后')

// 4. 空块按 / → 工具箱打开
await page.keyboard.press('/')
await page.waitForTimeout(400)
await state('S4: 按 / 后')

// 5. 非空段落按空格不应唤起 AI
await page.keyboard.press('Escape')
await page.keyboard.type('abc')
await page.keyboard.press(' ')
await page.waitForTimeout(300)
await state('S5: 非空段落按空格')

console.log(JSON.stringify(results, null, 2))
await browser.close()
