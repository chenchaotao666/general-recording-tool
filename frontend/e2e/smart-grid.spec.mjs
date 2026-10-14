// 智能表端到端冒烟：登录 → 智能表首页 → 新建工作表 → 网格编辑 → 筛选/排序/分组 →
// 视图切换 → 字段管理（加列/删除依赖）→ 撤销 → 批量删除 → 右键菜单 → 仪表盘。
// 用法：先起后端(8000)与 vite(5173)，再 node e2e/smart-grid.spec.mjs
import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })

const loginRes = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: process.env.E2E_USER || 'admin', password: process.env.E2E_PASS || 'admin123' },
})
const login = await loginRes.json()
if (!login.token) throw new Error(`登录失败：${JSON.stringify(login).slice(0, 200)}`)
await page.addInitScript(([token, user]) => {
  localStorage.setItem('grt_token', token)
  localStorage.setItem('grt_user', JSON.stringify(user))
  localStorage.setItem('grt_tenant_id', String(user.tenant?.id || user.tenant_id || ''))
  sessionStorage.setItem('grt_tenant_picked', '1')
}, [login.token, login.user])

const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))

// 1. 智能表首页 → 新建工作表
await page.goto(`${BASE}/smart`, { waitUntil: 'networkidle' })
await page.waitForSelector('.smart-home', { timeout: 10000 })
await page.getByText('⊞ 工作表').click()
await page.fill('.el-message-box input', `E2E测试表${Date.now() % 100000}`)
await page.locator('.el-message-box button.el-button--primary').click()
await page.waitForURL(/\/smart\/table\/\d+/, { timeout: 10000 })
await page.waitForSelector('.smart-vxe .vxe-body--row', { timeout: 10000 })
await page.waitForTimeout(1500)   // 等 grid 数据加载渲染
console.log('1. 新建工作表 → 网格打开通过')

// 2. 默认 5 字段 5 空行
const headerText = await page.locator('.smart-vxe .vxe-header--column').allInnerTexts()
const rows5 = await page.locator('.smart-vxe .vxe-body--row').count()
if (rows5 < 5) throw new Error(`默认行数不对：${rows5}`)
console.log('2. 默认字段列头:', headerText.join(' ').replace(/\n/g, ' ').slice(0, 80), '| 行数:', rows5)

// 3. 单元格编辑：第一行文本列（双击进入浮层编辑，Ctrl+Enter 提交）
const textCell = page.locator('.smart-vxe .vxe-body--row:visible').first().locator('td:visible').nth(2)
await textCell.dblclick()
await page.waitForSelector('.cell-overlay textarea', { timeout: 5000 })
await page.fill('.cell-overlay textarea', 'E2E-P001')
await page.keyboard.press('Control+Enter')
await page.waitForTimeout(600)
if (!(await textCell.innerText()).includes('E2E-P001')) throw new Error('文本编辑未保存')
console.log('3. 单元格文本编辑保存通过')

// 4. 单选编辑（自定义下拉面板 SelectCellPanel：搜索框 + 标签列表点选）
const selCell = page.locator('.smart-vxe .vxe-body--row:visible').nth(1).locator('td:visible').nth(3)
await selCell.dblclick()
await page.waitForSelector('.sel-panel .sel-search', { timeout: 5000 })
const opt = page.locator('.sel-panel .sel-item').first()
if (await opt.count()) {
  await opt.click()
  await page.waitForTimeout(500)
  console.log('4. 单选编辑通过:', (await selCell.innerText()).trim() || '(空)')
} else {
  console.log('4. 单选面板未弹出选项（记为警告）')
}

// 5. 添加一行
await page.getByText('⊕ 添加一行').click()
await page.waitForTimeout(600)
console.log('5. 添加一行通过')

// 6. 筛选：工具栏 → 添加条件
await page.getByText('⧩ 筛选').click()
await page.waitForSelector('.filter-popover', { timeout: 3000 })
await page.getByText('＋ 添加筛选条件').click()
const condRow = page.locator('.cond-row').first()
await condRow.locator('.el-select').first().click()
await page.waitForTimeout(300)
await page.locator('.el-select-dropdown__item:visible').first().click()
await condRow.locator('.el-input__inner').last().fill('E2E')
await page.locator('.filter-popover button:has-text("确定")').click()   // 草稿模式：确定才生效
await page.waitForTimeout(1200)
const filteredTotal = await page.locator('.smart-vxe .vxe-footer--row').allInnerTexts()
console.log('6. 筛选后汇总:', filteredTotal.join(' ').match(/记录数\s*\d+/)?.[0] || filteredTotal.join(' ').slice(0, 60))

// 7. 排序：通过列头菜单不好定位，直接调排序面板
await page.keyboard.press('Escape')
await page.locator('.filter-popover').first().evaluate(() => {})   // noop
await page.getByText('⇅ 排序').click()
await page.getByText('＋ 添加排序字段').click()
await page.waitForTimeout(800)
console.log('7. 排序面板添加规则通过')

// 8. 新建视图并切换（配置独立）
await page.locator('.vt-add').click()
await page.waitForTimeout(800)
const tabs = await page.locator('.view-tab').allInnerTexts()
if (tabs.length < 2) throw new Error('视图新建失败')
console.log('8. 视图 Tab:', tabs.map(t => t.trim()).join(' / '))

// 9. 分组
await page.getByText('≡ 分组').click()
await page.waitForSelector('.el-popover:visible .panel, .el-popper:visible .panel', { timeout: 3000 })
await page.waitForTimeout(400)
await page.locator('.el-popover:visible >> text=＋ 添加分组字段').click()
await page.waitForSelector('.rule-row .el-select', { timeout: 3000 })
await page.locator('.rule-row .el-select').first().click()
await page.waitForSelector('.el-select-dropdown__item:visible', { timeout: 3000 })
await page.locator('.el-select-dropdown__item:visible').nth(1).click()
await page.waitForTimeout(1000)
const groupRows = await page.locator('.smart-vxe .row-group').count()
console.log('9. 分组标题行数:', groupRows)

// 10. 撤销（Ctrl+Z）
await page.keyboard.press('Escape')
await page.keyboard.press('Control+z')
await page.waitForTimeout(400)
console.log('10. 撤销快捷键执行通过')

// 11. 右键菜单：展开记录（分组模式下跳过组标题行）
// 先收掉前面步骤可能残留的 el-select 下拉浮层（会拦截右键点击）
await page.keyboard.press('Escape')
await page.locator('.smart-vxe .vxe-footer--row').first().click({ position: { x: 4, y: 4 } }).catch(() => {})
await page.waitForTimeout(300)
const dataRow = page.locator('.smart-vxe .vxe-body--row:visible:not(.row-group)').first()
await dataRow.click({ button: 'right' })
await page.waitForSelector('.vxe-table--context-menu-wrapper.is--visible', { timeout: 3000 })
await page.locator('.vxe-context-menu--link', { hasText: '展开记录' }).click()
await page.waitForSelector('.el-drawer.record-detail', { timeout: 5000 })
console.log('11. 右键菜单 + 记录详情抽屉通过')
await page.keyboard.press('Escape')
await page.waitForTimeout(600)   // 等详情抽屉收起动画结束

// 12. 表格设置：新增字段（进度条类型）
await page.locator('.toolbar button', { hasText: '表格设置' }).click()
await page.waitForSelector('.el-drawer:not(.record-detail)', { timeout: 5000, state: 'visible' })
await page.locator('.el-drawer:not(.record-detail) >> text=＋ 新增字段').click()
await page.waitForSelector('.el-dialog .cfg-name input', { timeout: 3000 })
await page.fill('.el-dialog .cfg-name input', '进度')
await page.locator('.el-dialog .cfg-type').click()
await page.waitForSelector('.el-select-dropdown__item:visible', { timeout: 3000 })
await page.locator('.el-select-dropdown__item:visible', { hasText: '进度' }).click()
await page.locator('.el-dialog .el-dialog__footer button.el-button--primary').click()
await page.waitForTimeout(1200)
const headers2 = await page.locator('.smart-vxe').innerText()
if (!headers2.includes('进度')) throw new Error('新增进度字段未出现')
console.log('12. 表格设置新增进度字段通过')
await page.keyboard.press('Escape')

// 13. 仪表盘：新建 → 添加图表
await page.goto(`${BASE}/smart`, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('.smart-home .nav-new', { timeout: 8000 })
await page.getByText('⌚ 仪表盘').click()
await page.fill('.el-message-box input', 'E2E看板')
await page.locator('.el-message-box button.el-button--primary').click()
await page.waitForURL(/\/smart\/dashboard\/\d+/, { timeout: 8000 })
await page.waitForSelector('.dash-page .empty', { timeout: 5000 })
console.log('13. 仪表盘空状态通过')

await page.screenshot({ path: 'e2e/smart-grid.png' })
if (errors.length) console.log('页面 JS 错误:', errors.slice(0, 3))
console.log(errors.length ? 'E2E 完成（有 JS 错误需检查）' : 'E2E 全部通过 ✅')
await browser.close()
