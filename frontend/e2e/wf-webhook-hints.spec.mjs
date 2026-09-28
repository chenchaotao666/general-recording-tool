// 验证发送通知节点 webhook 类通道：按通道给标题/占位/获取提示 + URL 形态校验
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
await page.click('.palette-item:has-text("发送通知")')
await page.waitForTimeout(500)
await page.click('.vue-flow__node:has-text("发送通知")')
await page.waitForSelector('.config-panel .schema-form')

const panel = page.locator('.config-panel')
async function switchChannel(name) {
  await panel.locator('.el-form-item:has-text("通道") .el-select').click()
  await page.click(`.el-select-dropdown__item:has-text("${name}")`)
  await page.waitForTimeout(300)
}

// Webhook 通道
await switchChannel('Webhook')
const whItem = panel.locator('.el-form-item:has-text("Webhook 地址")')
check('webhook 通道标题「Webhook 地址」', await whItem.count() === 1)
check('webhook 提示 POST JSON 结构', (await whItem.locator('.field-hint').first().textContent()).includes('POST JSON'))
check('webhook 提示留空用默认', (await whItem.locator('.field-hint').first().textContent()).includes('设置'))

// 企业微信
await switchChannel('企业微信机器人')
const wcItem = panel.locator('.el-form-item:has-text("机器人 Webhook 地址")')
check('企业微信标题「机器人 Webhook 地址」', await wcItem.count() === 1)
check('企业微信占位是 qyapi 示例', (await wcItem.locator('input').getAttribute('placeholder')).includes('qyapi.weixin.qq.com'))
check('企业微信提示获取路径', (await wcItem.locator('.field-hint').first().textContent()).includes('群机器人'))

// 钉钉
await switchChannel('钉钉机器人')
const dtItem = panel.locator('.el-form-item:has-text("机器人 Webhook 地址")')
check('钉钉占位是 oapi 示例', (await dtItem.locator('input').getAttribute('placeholder')).includes('oapi.dingtalk.com'))
check('钉钉提示关键词坑', (await dtItem.locator('.field-hint').first().textContent()).includes('关键词'))

// URL 形态校验：非法显示红字，合法消失
await dtItem.locator('input').fill('not-a-url')
check('非法 URL 显示红色提示', await dtItem.locator('.field-hint.err').count() === 1)
await dtItem.locator('input').fill('https://oapi.dingtalk.com/robot/send?access_token=abc')
check('合法 URL 无红色提示', await dtItem.locator('.field-hint.err').count() === 0)

console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASS')
await browser.close()
process.exit(fails.length ? 1 : 0)
