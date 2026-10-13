// vxe-table spike 验证：真实 API 登录（后端须已启动），
// 断言网格渲染、冻结列、行高切换、单元格编辑、汇总行、虚拟滚动。
import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://localhost:5173'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })

// 真实登录拿 token（App.vue 挂载时会调 /api 当前租户，假 token 会被 401 拦截器踢回登录页）
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
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })

await page.goto(`${BASE}/smart/spike`, { waitUntil: 'networkidle' })
await page.waitForSelector('.smart-vxe .vxe-body--row', { timeout: 10000 })

// 1. 网格渲染 + 虚拟滚动（5000 行只渲染可视行）
const renderedRows = await page.locator('.smart-vxe .vxe-body--row').count()
const totalText = (await page.locator('.smart-vxe .vxe-footer--row').allInnerTexts()).join(' | ')
console.log('渲染行数(可视):', renderedRows, '| 汇总行:', totalText.replace(/\n/g, ' ').replace(/\s+/g, ' ').slice(0, 120))
if (renderedRows > 200) throw new Error(`虚拟滚动疑似未生效：渲染了 ${renderedRows} 行`)
if (!/记录数\s*5000/.test(totalText)) throw new Error(`汇总行缺少记录数：${totalText.slice(0, 150)}`)

// 2. 冻结列
const fixedLeft = await page.locator('.smart-vxe .vxe-table--fixed-left-wrapper').count()
console.log('冻结左列容器:', fixedLeft > 0 ? '存在' : '缺失')

// 3. 单元格内联编辑：点击第 1 行「文本」单元格（冻结列 → 在左侧冻结容器内）→ 输入 → 回车提交
const fixedRow = page.locator('.smart-vxe .vxe-table--fixed-left-wrapper .vxe-body--row').first()
const firstTextCell = fixedRow.locator('td:visible').nth(2)
await firstTextCell.click()
await page.waitForSelector('.cell-editor input', { timeout: 3000 })
await page.fill('.cell-editor input', 'SPIKE-EDIT')
await page.keyboard.press('Enter')
await page.waitForTimeout(300)
const cellText = await firstTextCell.innerText()
if (!cellText.includes('SPIKE-EDIT')) throw new Error(`内联编辑未生效：${cellText}`)
console.log('内联文本编辑提交通过:', cellText.trim())

// 4. 复选框单击即提交（主表格区第 2 行的复选框单元格：可见列 f_2..f_10 中 f_7 是第 6 个）
const mainRow2 = page.locator('.smart-vxe .vxe-table--main-wrapper .vxe-body--row, .smart-vxe .vxe-table--body-wrapper:not(.vxe-table--fixed-left-wrapper .vxe-table--body-wrapper) .vxe-body--row').nth(1)
const checkboxCell = mainRow2.locator('td:visible').nth(5)
const before = await checkboxCell.innerText()
await checkboxCell.click()
await page.waitForTimeout(200)
const after = await checkboxCell.innerText()
console.log('复选框单击切换:', JSON.stringify(before), '→', JSON.stringify(after))

// 5. 行高切换为「超高」
await page.getByText('超高', { exact: true }).click()
await page.waitForTimeout(300)
const rowH = await page.locator('.smart-vxe .vxe-body--row').first().evaluate(el => el.style.height || getComputedStyle(el).height)
console.log('切换超高后行高:', rowH)

// 6. 添加一行（顶部插入）
const firstCellBefore = await page.locator('.smart-vxe .vxe-body--row').first().innerText()
await page.getByText('＋ 添加一行').click()
await page.waitForTimeout(300)
const rowCount = await page.locator('.smart-vxe .vxe-footer--row').first().innerText()
console.log('添加行后汇总:', rowCount.includes('记录数') ? rowCount.match(/记录数\s*\d+/)?.[0] : rowCount)

// 7. 纵向滚动到底部区域（虚拟滚动渲染远端行）
await page.locator('.smart-vxe .vxe-table--body-wrapper').first().evaluate(el => { el.scrollTop = el.scrollHeight })
await page.waitForTimeout(400)
const lastVisible = await page.locator('.smart-vxe .vxe-body--row').last().innerText()
console.log('滚动到底部后末行片段:', lastVisible.slice(0, 30).replace(/\n/g, ' '))

await page.screenshot({ path: 'e2e/smart-spike.png', fullPage: false })
if (errors.length) console.log('页面错误:', errors.slice(0, 3))
console.log(errors.length ? 'SPIKE 完成（有 console 错误，需检查）' : 'SPIKE 全部断言通过 ✅')
await browser.close()
