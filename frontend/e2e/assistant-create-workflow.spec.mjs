// 验证 AI 助手 create_workflow 卡片：渲染 + 确认执行（拦截 API 模拟 LLM 产出）
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

// 拦截 chat：返回 create_workflow 卡片
await page.route('**/api/assistant/chat', (route) => route.fulfill({
  contentType: 'application/json',
  body: JSON.stringify({
    reply: '流程设计好了，确认后创建（默认停用）',
    action_card: {
      type: 'create_workflow',
      summary: '创建工作流「超期客户提醒」（2 个节点）',
      payload: {
        name: '超期客户提醒', description: '每日巡检',
        trigger: { type: 'cron', expr: '0 9 * * *' },
        nodes: [
          { id: 'q_1', type: 'query_records', name: '查超期客户', config: { table_id: 1 } },
          { id: 'send_1', type: 'send_message', name: '发通知', config: { channel: 'notify', template: 'x' } },
        ],
        edges: [{ from: 'q_1', to: 'send_1' }],
        notes: '说明文字',
      },
      warnings: [],
    },
  }),
}))
// 拦截 execute：返回创建成功
await page.route('**/api/assistant/execute', (route) => route.fulfill({
  contentType: 'application/json',
  body: JSON.stringify({ type: 'create_workflow', workflow_id: 999, name: '超期客户提醒' }),
}))

await page.goto(`${BASE}/tables`)
await page.waitForSelector('.ai-fab')
await page.click('.ai-fab')
const input = page.locator('.el-drawer textarea')
await input.waitFor({ timeout: 5000 })
await input.fill('帮我建一个每天早上提醒超期客户的流程')
await page.keyboard.press('Enter')
await page.waitForSelector('.card:has-text("创建工作流")', { timeout: 5000 })

const card = page.locator('.card:has-text("创建工作流")')
check('卡片标题含节点数', (await card.locator('.card-title').textContent()).includes('2 个节点'))
check('卡片显示名称输入框', await card.locator('input').count() >= 1)
check('卡片显示触发方式', (await card.textContent()).includes('定时'))
check('卡片列出节点', (await card.textContent()).includes('查超期客户') && (await card.textContent()).includes('发通知'))

// 确认创建
await card.locator('button:has-text("确认创建")').click()
await page.waitForSelector('.done-text a[href="/workflows/999/edit"]', { timeout: 5000 })
check('创建成功提示含编辑器链接', true)

console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASS')
await browser.close()
process.exit(fails.length ? 1 : 0)
