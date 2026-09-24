// 验证：点击面板外 → AI 面板隐藏；点击面板内 → 保持打开
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
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.press(' ')
await page.waitForTimeout(300)

const s1 = await page.evaluate(() => !!document.querySelector('.ai-panel'))

// 点击面板内的输入框 → 保持打开
await page.click('.ai-panel .ai-input')
await page.waitForTimeout(200)
const s2 = await page.evaluate(() => !!document.querySelector('.ai-panel'))

await page.evaluate(() => { window.__ev=[]; document.addEventListener('mousedown',(e)=>window.__ev.push(e.target.className||e.target.tagName), true) })
// 点击编辑器其他位置（标题输入框）→ 面板隐藏
await page.click('.title-input')
await page.waitForTimeout(300)
const s3 = await page.evaluate(() => ({ ev: window.__ev, panel: !!document.querySelector('.ai-panel') }))

// 再打开，点击文档块区域 → 隐藏且焦点正常落入编辑器
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.press(' ')
await page.waitForTimeout(300)
await page.click('.editor-holder .ce-paragraph')
await page.waitForTimeout(300)
const s4 = await page.evaluate(() => ({
  hidden: !document.querySelector('.ai-panel'),
  caretInEditor: document.querySelector('.editor-holder')?.contains(document.activeElement),
}))

console.log(JSON.stringify({
  'S1 打开后面板存在': s1,
  'S2 点击面板内仍打开': s2,
  'S3 点击面板外已隐藏': s3,
  'S4 再打开点编辑器块': s4,
}, null, 2))
await browser.close()
