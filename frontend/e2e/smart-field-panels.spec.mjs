import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const base = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  page.setDefaultTimeout(10000)
  const login = await (await page.request.post(`${base}/api/auth/login`, { data: { username: process.env.E2E_USER || 'admin', password: process.env.E2E_PASS || 'admin123' } })).json()
  assert.ok(login.token)
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem('grt_token', token)
    localStorage.setItem('grt_user', JSON.stringify(user))
    localStorage.setItem('grt_tenant_id', String(user.tenant?.id || user.tenant_id || ''))
    sessionStorage.setItem('grt_tenant_picked', '1')
  }, login)
  let fields
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch(), meta = await response.json()
    const field = meta.fields.find(f => f.field_type === 'text')
    fields = [{ ...field, field_name: 'plain', label: 'Plain field' },
      { ...field, id: 99001, field_name: 'ai_panel', label: 'AI field', field_type: 'ai', options: { scene: 'summary', outputType: 'text', inputFields: ['plain'] } }]
    meta.fields = fields
    await route.fulfill({ response, json: meta })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch(), data = await response.json()
    data.fields = fields; data.items = [{ id: 99001, plain: 'Example' }]; data.total = 1; data.grouped = false
    data.view.config = { ...data.view.config, fieldOrder: ['plain', 'ai_panel'], hiddenFields: [], fieldVisibility: {}, frozenFields: [], groups: [] }
    await route.fulfill({ response, json: data })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  async function drag(panel, handle, dx = 90, dy = 65) {
    const before = await panel.boundingBox(), area = await handle.boundingBox()
    await page.mouse.move(area.x + area.width / 2, area.y + area.height / 2)
    await page.mouse.down()
    await page.mouse.move(area.x + area.width / 2 + dx, area.y + area.height / 2 + dy, { steps: 8 })
    await page.mouse.up()
    const after = await panel.boundingBox()
    assert.ok(Math.abs(after.x - before.x - dx) < 3, `horizontal movement ${after.x - before.x}`)
    assert.ok(Math.abs(after.y - before.y - dy) < 3, `vertical movement ${after.y - before.y}`)
  }
  const plain = page.locator('th.vxe-header--column:visible').filter({ hasText: 'Plain field' }).first()
  await plain.dblclick()
  const dialog = page.locator('.el-dialog.st-fcd:visible')
  await dialog.waitFor(); await page.waitForTimeout(350)
  assert.equal(Math.round((await dialog.boundingBox()).width), 320)
  await drag(dialog, dialog.locator('[data-panel-drag-handle]'))
  await dialog.locator('.fcd-name').fill('Unsaved name')
  assert.equal(await dialog.locator('.fcd-name').inputValue(), 'Unsaved name')
  await page.keyboard.press('Escape')
  await plain.click({ button: 'right' })
  await page.locator('.field-menu-layer .mi').filter({ hasText: /^新建编组$/ }).click()
  await page.locator('.gd-form').waitFor(); await page.waitForTimeout(350)
  assert.equal(Math.round((await dialog.boundingBox()).width), 320)
  const assertNoOverflow = async () => {
    const sizes = await dialog.evaluate(el => ({ scroll: el.scrollWidth, client: el.clientWidth }))
    assert.ok(sizes.scroll <= sizes.client, `Group panel overflows: ${sizes.scroll} > ${sizes.client}`)
  }
  await assertNoOverflow()
  await drag(dialog, dialog.locator('[data-panel-drag-handle]'))
  await assertNoOverflow()
  await page.setViewportSize({ width: 360, height: 280 })
  await page.waitForTimeout(200)
  const smallGroup = await dialog.boundingBox()
  assert.ok(smallGroup.x >= 11 && smallGroup.y >= 11 && smallGroup.x + smallGroup.width <= 349 && smallGroup.y + smallGroup.height <= 269, JSON.stringify(smallGroup))
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await page.setViewportSize({ width: 1600, height: 1000 })
  const ai = page.locator('th.vxe-header--column:visible').filter({ hasText: 'AI field' }).first()
  const rect = await ai.boundingBox()
  const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2
  await page.mouse.dblclick(x, y)
  const editor = page.locator('.afe')
  await editor.waitFor(); await page.waitForTimeout(350)
  const opened = await editor.boundingBox()
  assert.ok(Math.abs(opened.x - Math.max(12, Math.min(x + 4, 988))) < 2, 'AI panel follows double-click x')
  assert.ok(Math.abs(opened.y - Math.max(12, Math.min(y + 4, 428))) < 2, 'AI panel follows double-click y')
  await drag(editor, editor.locator('.afe-head .afe-flex'), 80, 35)
  await editor.locator('.afe-name').fill('Unsaved AI name')
  await editor.getByLabel('关闭', { exact: true }).click()
  console.log('PASS: normal and group panels are 320px and draggable; AI follows double-click and supports dragging and input.')
} finally { await browser.close() }
