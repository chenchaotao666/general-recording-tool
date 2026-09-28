// 复现：邮件通道填邮箱 → 切短信 → 邮箱残留在接收手机号里（内容串通道）
import { chromium } from 'playwright'

const BASE = 'http://localhost:5177'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })

const login = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const { token, user } = await login.json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => {
  localStorage.setItem('grt_token', t)
  localStorage.setItem('grt_user', JSON.stringify(u))
}, [token, user])
await page.goto(`${BASE}/workflows/new`)
await page.waitForSelector('.wf-editor')
await page.click('.palette-item:has-text("发送通知")')
await page.waitForTimeout(500)
await page.click('.vue-flow__node:has-text("发送通知")')
await page.waitForSelector('.config-panel .schema-form')

const panel = page.locator('.config-panel')
// 邮件通道填入邮箱
await panel.locator('.el-form-item:has-text("通道") .el-select').click()
await page.click('.el-select-dropdown__item:has-text("邮件")')
const recipItem = panel.locator('.el-form-item:has-text("接收邮箱")')
await recipItem.locator('.el-select__wrapper').click()
await page.keyboard.type('a@b.com')
await page.keyboard.press('Enter')

// 切到短信，看接收手机号里残留什么
await panel.locator('.el-form-item:has-text("通道") .el-select').click()
await page.click('.el-select-dropdown__item:has-text("短信")')
await page.waitForTimeout(300)
const smsTags = await panel.locator('.el-form-item:has-text("接收手机号") .el-tag').allTextContents()
console.log('切到短信后的标签:', JSON.stringify(smsTags))
const ok = smsTags.length === 0
console.log(ok ? 'PASS  切换通道后残留已清空' : 'FAIL  邮箱串进了短信通道')

// 反向：短信填手机号 → 切回邮件 → 同样清空
const smsItem = panel.locator('.el-form-item:has-text("接收手机号")')
await smsItem.locator('.el-select__wrapper').click()
await page.keyboard.type('13800138000')
await page.keyboard.press('Enter')
await panel.locator('.el-form-item:has-text("通道") .el-select').click()
await page.click('.el-select-dropdown__item:has-text("邮件")')
await page.waitForTimeout(300)
const mailTags = await panel.locator('.el-form-item:has-text("接收邮箱") .el-tag').allTextContents()
console.log('切回邮件后的标签:', JSON.stringify(mailTags))
const ok2 = mailTags.length === 0
console.log(ok2 ? 'PASS  反向切换同样清空' : 'FAIL  手机号串进了邮件通道')

await browser.close()
process.exit(ok && ok2 ? 0 : 1)
