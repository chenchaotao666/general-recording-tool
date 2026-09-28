// 验证发送通知节点：邮件/短信通道下接收人是标签式录入，无「插入变量」
import { chromium } from 'playwright'

const BASE = 'http://localhost:5177'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
const fails = []
const check = (name, cond, extra = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`)
  if (!cond) fails.push(name)
}

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

// 点击节点面板的「发送通知」加入画布并选中
await page.click('.palette-item:has-text("发送通知")')
await page.waitForTimeout(500)
await page.click('.vue-flow__node:has-text("发送通知")')
await page.waitForSelector('.config-panel .schema-form')

// 切通道为「邮件」
const panel = page.locator('.config-panel')
await panel.locator('.el-form-item:has-text("通道") .el-select').click()
await page.waitForSelector('.el-select-dropdown__item')
await page.click('.el-select-dropdown__item:has-text("邮件")')
await page.waitForTimeout(300)

// 1. 接收邮箱出现，且是标签式多选（不是模板文本框）
const recipItem = panel.locator('.el-form-item:has-text("接收邮箱")')
check('邮件通道显示「接收邮箱」', await recipItem.count() === 1)
check('接收人是标签式多选', await recipItem.locator('.el-select__tags, .el-select__selected-item').count() > 0)
check('接收人不是模板文本框', await recipItem.locator('textarea').count() === 0)

// 2. 该字段下没有「插入变量」
check('接收人无插入变量按钮', await recipItem.locator('text=插入变量').count() === 0)

// 3. 录入合法邮箱成标签，非法被拒
await recipItem.locator('.el-select__wrapper').click()
await page.keyboard.type('a@b.com')
await page.keyboard.press('Enter')
await page.keyboard.type('not-an-email')
await page.keyboard.press('Enter')
await page.waitForTimeout(300)
const tags = await recipItem.locator('.el-tag').allTextContents()
check('合法邮箱成标签、非法被拒', tags.length === 1 && tags[0].includes('a@b.com'), JSON.stringify(tags))

// 4. 切到短信：标题变「接收手机号」，手机号校验生效
await panel.locator('.el-form-item:has-text("通道") .el-select').click()
await page.click('.el-select-dropdown__item:has-text("短信")')
await page.waitForTimeout(300)
const smsItem = panel.locator('.el-form-item:has-text("接收手机号")')
check('短信通道显示「接收手机号」', await smsItem.count() === 1)
await smsItem.locator('.el-select__wrapper').click()
await page.keyboard.type('13800138000')
await page.keyboard.press('Enter')
await page.keyboard.type('abc')
await page.keyboard.press('Enter')
await page.waitForTimeout(300)
const smsTags = await smsItem.locator('.el-tag').allTextContents()
check('手机号成标签、字母被拒', smsTags.length === 1 && smsTags[0].includes('13800138000'), JSON.stringify(smsTags))

console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASS')
await browser.close()
process.exit(fails.length ? 1 : 0)
