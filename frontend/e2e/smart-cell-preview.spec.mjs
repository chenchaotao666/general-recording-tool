// 文本单元格单击预览 e2e：单击文本格 → 编辑同款浮层只读展示全文（readonly+禁选）；
// 双击浮层 → 进入可编辑状态；Esc/失焦关闭不写回。
// 用法：先起后端(8000)与 vite(5173)，再 node e2e/smart-cell-preview.spec.mjs
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

// 新建工作表并写入长文本
await page.goto(`${BASE}/smart`, { waitUntil: 'networkidle' })
await page.waitForSelector('.smart-home', { timeout: 10000 })
await page.getByText('⊞ 工作表').click()
await page.fill('.el-message-box input', `预览测试${Date.now() % 100000}`)
await page.locator('.el-message-box button.el-button--primary').click()
await page.waitForURL(/\/smart\/table\/\d+/, { timeout: 10000 })
await page.waitForSelector('.smart-vxe .vxe-body--row', { timeout: 10000 })
await page.waitForTimeout(1500)

const textCell = page.locator('.smart-vxe .vxe-body--row:visible').first().locator('td:visible').nth(2)
await textCell.dblclick()
await page.waitForSelector('.cell-overlay textarea', { timeout: 5000 })
await page.fill('.cell-overlay textarea', '洛阳市涧西区建设路40号院3栋2单元501室，一段足够长的地址文本用来触发省略号显示')
await page.keyboard.press('Control+Enter')
await page.waitForTimeout(600)

// 1. 单击文本格 → 预览浮层（div 禁选、preview 类、内容完整）
await textCell.click()
await page.waitForSelector('.cell-overlay.preview .preview-text', { timeout: 5000 })
const pv = page.locator('.cell-overlay.preview .preview-text')
const val = await pv.innerText()
if (!val.includes('一段足够长的地址文本')) throw new Error('预览内容不完整')
// 拖拽尝试选中 → 应为空
const box = await pv.boundingBox()
await page.mouse.move(box.x + 8, box.y + box.height / 2)
await page.mouse.down()
await page.mouse.move(box.x + box.width - 8, box.y + box.height / 2, { steps: 8 })
await page.mouse.up()
const sel = await page.evaluate(() => window.getSelection().toString())
if (sel) throw new Error(`预览态不应能选中文字，实际选中了：${sel}`)
console.log('1. 单击 → 只读全文预览浮层（禁选）通过')

// 2. 双击浮层 → 进入编辑态（readonly 解除，可输入）
await page.locator('.cell-overlay.preview').dblclick()
await page.waitForTimeout(500)
const editTa = page.locator('.cell-overlay:not(.preview) textarea')
if (!(await editTa.count())) throw new Error('双击预览浮层未进入编辑态')
await editTa.fill('改了内容-E2E')
await page.keyboard.press('Control+Enter')
await page.waitForTimeout(600)
if (!(await textCell.innerText()).includes('改了内容-E2E')) throw new Error('编辑未保存')
console.log('2. 双击浮层 → 编辑并保存通过')

// 3. 再单击 → 预览；Esc 关闭且不改值
await textCell.click()
await page.waitForSelector('.cell-overlay.preview .preview-text', { timeout: 5000 })
await page.keyboard.press('Escape')
await page.waitForTimeout(400)
if (await page.locator('.cell-overlay').count()) throw new Error('Esc 后预览未关闭')
if (!(await textCell.innerText()).includes('改了内容-E2E')) throw new Error('Esc 不应改值')
console.log('3. Esc 关闭预览且不写回通过')

await browser.close()
console.log('全部通过')
