// 验证 AI 面板内嵌文档流：是 ce-block 的兄弟节点、实际占位、不被裁剪
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
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
// 输入一行，再 Enter 一个空块，在空块上唤起 AI
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.type('第一行内容')
await page.keyboard.press('Enter')
await page.keyboard.press(' ')
await page.waitForTimeout(400)

const d = await page.evaluate(() => {
  const panel = document.querySelector('.ai-panel')
  const anchor = document.querySelector('.ai-anchor')
  const redactor = document.querySelector('.codex-editor__redactor')
  const holder = document.querySelector('.editor-holder')
  const pr = panel?.getBoundingClientRect()
  const hr = holder?.getBoundingClientRect()
  return {
    panelExists: !!panel,
    inRedactor: !!(panel && redactor?.contains(panel)),
    anchorIsBlockSibling: anchor?.parentElement === redactor,
    anchorAfterSecondBlock: anchor?.previousElementSibling === document.querySelectorAll('.ce-block')[1],
    // 面板完全在 editor-holder 可视范围内（不被裁剪）
    fullyVisible: !!(pr && hr && pr.top >= hr.top && pr.bottom <= hr.bottom + 1),
    panelHeight: pr?.height,
  }
})
console.log(JSON.stringify(d, null, 2))
await browser.close()
