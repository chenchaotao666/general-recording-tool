// 验证任务规则下线后的系统：菜单无任务规则、/tasks 不再可达、查询记录节点有 AI 筛选、变量面板有表格渲染项
import { chromium } from 'playwright'

const BASE = 'http://localhost:5180'
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

// 1. 菜单里没有「任务规则」
await page.goto(`${BASE}/tables`)
await page.waitForSelector('.el-menu')
const menuText = await page.$eval('.el-menu', (el) => el.textContent)
check('菜单无任务规则', !menuText.includes('任务规则'))

// 2. /api/tasks 后端已下线（404）
const apiRes = await page.request.get(`${BASE}/api/tasks`, {
  headers: { Authorization: `Bearer ${token}` },
})
check('/api/tasks 已下线', apiRes.status() === 404, `status=${apiRes.status()}`)

// 3. 查询记录节点有「AI 筛选」输入区
await page.goto(`${BASE}/workflows/new`)
await page.waitForSelector('.wf-editor')
await page.click('.palette-item:has-text("查询记录")')
await page.waitForTimeout(500)
await page.click('.vue-flow__node:has-text("查询记录")')
await page.waitForSelector('.config-panel .schema-form')
const panel = page.locator('.config-panel')
check('配置面板有 AI 筛选', await panel.locator('.el-form-item:has-text("AI 筛选")').count() === 1)
check('AI 筛选有候选上限提示', (await panel.locator('.el-form-item:has-text("AI 筛选") .field-hint').textContent()).includes('200'))

// 4. 变量面板有「记录列表（表格）」渲染项（用 API 建一个 查询→通知 已连线的流程再开编辑器）
const tables = await page.request.get(`${BASE}/api/tables`, { headers: { Authorization: `Bearer ${token}` } })
const tableId = (await tables.json())[0].id
const wfRes = await page.request.post(`${BASE}/api/workflows`, {
  headers: { Authorization: `Bearer ${token}` },
  data: {
    name: '变量面板测试', enabled: false,
    trigger: { type: 'manual' },
    nodes: [
      { id: 'q_1', type: 'query_records', name: '查', config: { table_id: tableId, limit: 10 } },
      { id: 'send_1', type: 'send_message', name: '发', config: { channel: 'notify', template: 'x' } },
    ],
    edges: [{ from: 'q_1', to: 'send_1' }],
  },
})
const wfId = (await wfRes.json()).id
await page.goto(`${BASE}/workflows/${wfId}/edit`)
await page.waitForSelector('.wf-editor')
await page.waitForFunction(() => document.querySelectorAll('.vue-flow__node').length >= 3, { timeout: 10000 })
await page.waitForTimeout(500)
const sendNode = page.locator('.vue-flow__node').nth(2)
await sendNode.scrollIntoViewIfNeeded()
await sendNode.click()
await page.waitForSelector('.config-panel .schema-form')
const panel2 = page.locator('.config-panel')
await panel2.locator('.el-form-item:has-text("内容模板") textarea').click()
await panel2.locator('.el-form-item:has-text("内容模板") button:has-text("插入变量")').click()
await page.waitForTimeout(400)
const varPanelText = await page.evaluate(() => document.body.textContent)
check('变量面板有表格渲染项', varPanelText.includes('记录列表（表格）'))
check('变量面板有编号清单项', varPanelText.includes('记录列表（编号清单）'))
await page.request.delete(`${BASE}/api/workflows/${wfId}`, { headers: { Authorization: `Bearer ${token}` } })

console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASS')
await browser.close()
process.exit(fails.length ? 1 : 0)
