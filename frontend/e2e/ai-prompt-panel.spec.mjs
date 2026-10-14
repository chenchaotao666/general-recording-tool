// AiPromptPanel 统一面板冒烟：四个入口都渲染浮动面板（贴按钮弹出/可拖动/Esc 关闭），业务差异内容在位
import { chromium } from 'playwright'
const BASE = 'http://localhost:5173'
const results = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('pageerror', (e) => results.push(['pageerror', String(e).slice(0, 150)]))
const step = (name, ok, extra = '') => { results.push([name, ok]); console.log(`${ok ? '✓' : '✗'} ${name} ${extra}`) }

const login = await page.request.post(`${BASE}/api/auth/login`, { data: { username: 'admin', password: 'admin123' } })
const { token, user } = await login.json()
const headers = { Authorization: `Bearer ${token}` }
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => { localStorage.setItem('grt_token', t); localStorage.setItem('grt_user', JSON.stringify(u)) }, [token, user])

// 通用断言：面板出现 + 贴按钮（垂直距离合理）+ 拖动 + Esc 关闭
async function checkPanel(name, btnSelector) {
  const btn = page.locator(btnSelector).first()
  await btn.waitFor({ state: 'visible', timeout: 15000 })
  const btnBox = await btn.boundingBox()
  await btn.click()
  await page.waitForSelector('.ai-pp', { timeout: 5000 })
  const pBox = await page.locator('.ai-pp').boundingBox()
  const near = pBox && btnBox && Math.abs(pBox.y - (btnBox.y + btnBox.height)) < 80
  step(`${name} 面板贴按钮弹出`, !!near, near ? '' : `panel.y=${pBox?.y} btn.bottom=${btnBox ? btnBox.y + btnBox.height : '?'}`)
  // 拖动标题栏（往左拖：按钮多在右侧，往左才有活动空间）
  await page.mouse.move(pBox.x + 100, pBox.y + 15)
  await page.mouse.down()
  await page.mouse.move(pBox.x - 120, pBox.y + 80, { steps: 5 })
  await page.mouse.up()
  const pBox2 = await page.locator('.ai-pp').boundingBox()
  step(`${name} 面板可拖动`, Math.abs(pBox2.x - pBox.x) > 50 || Math.abs(pBox2.y - pBox.y) > 30)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
  step(`${name} Esc 关闭`, await page.locator('.ai-pp').count() === 0)
}

// 1. 思维导图（先选中节点再开面板：上下文条 + 建议操作 chips）
const mm = await (await page.request.post(`${BASE}/api/mindmaps`, {
  headers, data: { title: '面板冒烟导图', data: { text: '中心主题', children: [{ text: '分支A', children: [] }, { text: '分支B', children: [] }] } },
})).json()
await page.goto(`${BASE}/mindmaps/${mm.id}`)
await page.waitForSelector('.smm-node', { timeout: 20000 })
await page.click('.mm-canvas :text("分支A")')   // 选中节点
await page.waitForTimeout(300)
await checkPanel('思维导图', '.ai-btn')
await page.click('.mm-canvas :text("分支A")')
await page.waitForTimeout(300)
await page.click('.ai-btn')
await page.waitForSelector('.ai-pp')
step('思维导图 选中节点有上下文条', await page.locator('.ai-pp .ai-pp-context:has-text("基于选中节点")').count() === 1)
const mmChips = await page.locator('.ai-pp .ai-pp-chip').allTextContents()
step('思维导图 选中时建议项针对节点（扩写/优化/改写）', mmChips.some((c) => c.includes('扩写')) && mmChips.some((c) => c.includes('优化')) && mmChips.some((c) => c.includes('改写')) && mmChips.some((c) => c.includes('总结当前导图全文')), mmChips.join('/'))
step('思维导图 选中时不显示整图示例 chips', !mmChips.some((c) => c.includes('调研一个主题')))
step('思维导图 左下角快捷键提示', await page.locator('.ai-pp .ai-pp-hint').textContent().then((t) => t.includes('Enter 生成') && t.includes('Esc 取消')))
// 点建议项只填入输入框，不直接生成（面板仍在、无请求发出）
await page.click('.ai-pp .ai-pp-chip:has-text("扩写")')
await page.waitForTimeout(400)
const filled = await page.locator('.ai-pp textarea').inputValue()
step('思维导图 点建议项只填入不生成', filled.includes('扩写') && await page.locator('.ai-pp').count() === 1 && await page.locator('.ai-pp .ai-pp-hint:has-text("生成中")').count() === 0, filled)
await page.screenshot({ path: 'e2e/out-ai-panel-mm.png' })
await page.keyboard.press('Escape')
// 未选中（点空白画布取消选择）→ 显示 XMind 同款整图示例 chips
await page.mouse.click(1100, 780)
await page.waitForTimeout(300)
await page.click('.ai-btn')
await page.waitForSelector('.ai-pp')
const mmChips0 = await page.locator('.ai-pp .ai-pp-chip').allTextContents()
step('思维导图 未选中时显示 XMind 示例 chips', ['调研一个主题并总结要点', '把一个项目拆解成执行计划', '探索某个领域的最新趋势', '分析我的思维导图，给出改进建议', '总结当前导图全文'].every((t) => mmChips0.some((c) => c.includes(t))), mmChips0.join('/'))
// 总结也是建议项：只填入不执行、不弹框
await page.click('.ai-pp .ai-pp-chip:has-text("总结当前导图全文")')
await page.waitForTimeout(400)
const filledSum = await page.locator('.ai-pp textarea').inputValue()
step('思维导图 总结建议项只填入不执行不弹框', filledSum.includes('总结当前导图全文') && await page.locator('.ai-pp').count() === 1 && await page.locator('.el-dialog:has-text("导图总结")').count() === 0, filledSum)
await page.keyboard.press('Escape')
// 提交总结：结果在面板内展示（mock 后端，不依赖真实 LLM；回归「不再弹框」）
await page.route('**/api/mindmaps/ai-assist', (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ summary: '这是 mock 总结内容，面板内展示。' }) }))
await page.click('.ai-btn')
await page.waitForSelector('.ai-pp')
await page.click('.ai-pp .ai-pp-chip:has-text("总结当前导图全文")')
await page.keyboard.press('Enter')
await page.waitForSelector('.ai-pp .ai-pp-result', { timeout: 8000 })
const mmResText = await page.locator('.ai-pp .ai-pp-result-body').textContent()
step('思维导图 总结结果在面板内展示', mmResText.includes('mock 总结') && await page.locator('.el-dialog').count() === 0, mmResText.slice(0, 30))
await page.screenshot({ path: 'e2e/out-ai-panel-mm-result.png' })
await page.unroute('**/api/mindmaps/ai-assist')
await page.keyboard.press('Escape')
// 多选：左键框选两个分支节点 → 上下文条列出全部选中，不提供单节点扩写/改写
const boxA = await page.locator('.mm-canvas :text("分支A")').boundingBox()
const boxB = await page.locator('.mm-canvas :text("分支B")').boundingBox()
const sx = Math.min(boxA.x, boxB.x) - 60
const sy = Math.min(boxA.y, boxB.y) - 60
await page.mouse.move(sx, sy)
await page.mouse.down()
await page.mouse.move(Math.max(boxA.x + boxA.width, boxB.x + boxB.width) + 60, Math.max(boxA.y + boxA.height, boxB.y + boxB.height) + 60, { steps: 8 })
await page.mouse.up()
await page.waitForTimeout(300)
await page.click('.ai-btn')
await page.waitForSelector('.ai-pp')
const ctxText = await page.locator('.ai-pp .ai-pp-context').textContent()
const mmChipsMulti = await page.locator('.ai-pp .ai-pp-chip').allTextContents()
step('思维导图 多选上下文条列出全部节点', ctxText.includes('已选中 2 个节点') && ctxText.includes('分支A') && ctxText.includes('分支B'), ctxText)
step('思维导图 多选提供批量优化/选中分支总结（无单节点操作）',
  mmChipsMulti.some((c) => c.includes('优化这 2 个节点')) && mmChipsMulti.some((c) => c.includes('总结这 2 个分支'))
  && !mmChipsMulti.some((c) => c.includes('扩写')) && !mmChipsMulti.some((c) => c.includes('改写')), mmChipsMulti.join('/'))
// 多选点建议项同样只填入不生成
await page.click('.ai-pp .ai-pp-chip:has-text("优化这 2 个节点")')
await page.waitForTimeout(400)
const filledMulti = await page.locator('.ai-pp textarea').inputValue()
step('思维导图 多选点建议项只填入不生成', filledMulti.includes('优化这些分支') && await page.locator('.ai-pp').count() === 1, filledMulti.slice(0, 30))
await page.click('.ai-pp .ai-pp-chip:has-text("总结这 2 个分支")')
await page.waitForTimeout(400)
const filledSumSel = await page.locator('.ai-pp textarea').inputValue()
step('思维导图 多选总结建议项只填入不弹框', filledSumSel.includes('总结这几个分支') && await page.locator('.el-dialog').count() === 0, filledSumSel)
await page.keyboard.press('Escape')

// 2. 画板
const wb = await (await page.request.post(`${BASE}/api/whiteboards`, {
  headers, data: { title: '面板冒烟画板', engine: 'excalidraw' },
})).json()
await page.goto(`${BASE}/whiteboard?wbId=${wb.id}`)
await page.waitForSelector('.excalidraw', { timeout: 30000 })
await checkPanel('画板', 'button:has-text("AI 生成")')
await page.click('button:has-text("AI 生成")')
await page.waitForSelector('.ai-pp')
step('画板 五档模式在位', await page.locator('.ai-pp .el-radio-button').count() === 5)
await page.screenshot({ path: 'e2e/out-ai-panel-wb.png' })
await page.keyboard.press('Escape')

// 3. 报表列表
await page.goto(`${BASE}/reports`)
await page.waitForSelector('.ai-btn')
await checkPanel('报表', '.ai-btn')
await page.click('.ai-btn')
await page.waitForSelector('.ai-pp')
step('报表 面板含表选择器', await page.locator('.ai-pp .el-select').count() === 1)
await page.keyboard.press('Escape')

// 4. 工作流列表
await page.goto(`${BASE}/workflows`)
await page.waitForSelector('.ai-btn')
await checkPanel('工作流', '.ai-btn')
await page.click('.ai-btn')
await page.waitForSelector('.ai-pp')
step('工作流 示例 chips 在位', await page.locator('.ai-pp .ai-pp-chip').count() === 3)
step('工作流 提交文案保留业务差异', await page.locator('.ai-pp button:has-text("生成并进入画布")').count() === 1)
await page.screenshot({ path: 'e2e/out-ai-panel-wf.png' })
await page.keyboard.press('Escape')

await page.request.delete(`${BASE}/api/mindmaps/${mm.id}`, { headers })
await page.request.delete(`${BASE}/api/whiteboards/${wb.id}`, { headers })
await browser.close()
const failed = results.filter(([n, ok]) => ok !== true)
console.log(failed.length ? `FAIL (${failed.map((f) => f[0]).join('；')})` : 'PASS')
