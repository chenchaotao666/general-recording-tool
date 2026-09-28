// 验证节点说明对话框：功能/输入/输出三段 + 输出变量带节点 id + 常见报错（发送通知）
import { chromium } from 'playwright'

const BASE = 'http://localhost:5182'
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

// 加「发送通知」节点并选中
await page.click('.palette-item:has-text("发送通知")')
await page.waitForTimeout(500)
await page.click('.vue-flow__node:has-text("发送通知")')
await page.waitForSelector('.config-panel .schema-form')

// 打开节点说明
await page.click('.config-panel button:has-text("节点说明")')
await page.waitForSelector('.el-dialog:has-text("节点说明")')
const dlg = page.locator('.el-dialog:has-text("节点说明")')
const text = await dlg.textContent()
check('有功能段', text.includes('功能') && text.includes('发送消息'))
check('有输入段', text.includes('输入（配置项）') && text.includes('通道'))
check('有输出段', text.includes('输出（下游节点可引用'))
check('输出变量带节点 id', await dlg.locator('code.expr:has-text("{nodes.")').count() >= 1)
check('有常见报错段', text.includes('常见报错') && text.includes('短信网关'))

// 关掉，换「查询记录」节点：输出应有 records 且带表格渲染提示
await page.keyboard.press('Escape')
await page.click('.palette-item:has-text("查询记录")')
await page.waitForTimeout(500)
await page.click('.vue-flow__node:has-text("查询记录")')
await page.waitForTimeout(400)
await page.click('.config-panel button:has-text("节点说明")')
await page.waitForTimeout(400)
const dlg2 = page.locator('.el-dialog:has-text("节点说明")')
const text2 = await dlg2.textContent()
check('查询节点输出含 records', text2.includes('records'))
check('数组输出有表格渲染提示', text2.includes('渲染成表格'))
check('AI 筛选出现在输入说明', text2.includes('AI 筛选'))

console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASS')
await browser.close()
process.exit(fails.length ? 1 : 0)
