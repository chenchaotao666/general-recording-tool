import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const base = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const res = await page.request.post(`${base}/api/auth/login`, { data: { username: process.env.E2E_USER || 'admin', password: process.env.E2E_PASS || 'admin123' } })
  const login = await res.json()
  assert.ok(login.token, 'Login failed')
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem('grt_token', token)
    localStorage.setItem('grt_user', JSON.stringify(user))
    localStorage.setItem('grt_tenant_id', String(user.tenant?.id || user.tenant_id || ''))
    sessionStorage.setItem('grt_tenant_picked', '1')
  }, login)
  let field
  let fixtureFields
  let searchRequests = 0
  const insertRequests = []
  await page.route(/\/api\/smart\/tables\/\d+\/records\/\d+\/insert$/, async route => {
    insertRequests.push(route.request().postDataJSON())
    await route.fulfill({ json: { ids: [901] } })
  })
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch()
    const meta = await response.json()
    field = meta.fields.find(f => f.field_type === 'text')?.field_name
    assert.ok(field, 'Need an existing table with a text field')
    const template = meta.fields.find(f => f.field_name === field)
    fixtureFields = Array.from({ length: 26 }, (_, i) => ({ ...template, id: 9000 + i, field_name: `find_col_${i}`, label: `Search column ${i}` }))
    field = fixtureFields.at(-1).field_name
    meta.fields = fixtureFields
    await route.fulfill({ response, json: meta })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    data.items = Array.from({ length: 180 }, (_, i) => 901 + i).map(id => ({ id, [field]: `search-fixture-${id}` }))
    data.fields = fixtureFields
    data.total = 400
    data.grouped = false
    data.view.config = { ...data.view.config, rowHeight: process.env.SNAP_ROW_HEIGHT || 'default', hiddenFields: [], fieldVisibility: {}, fieldOrder: fixtureFields.map(f => f.field_name), frozenFields: [], groups: [] }
    await route.fulfill({ response, json: data })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/search-replace$/, async route => {
    searchRequests++
    assert.equal(route.request().postDataJSON().replace, undefined)
    await route.fulfill({ json: { matches: [903, 901, 902].map(recordId => ({ recordId, field, fieldType: 'text', value: `search-fixture-${recordId}`, replaceable: true })) } })
  })

  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.waitForURL(/\/smart\/table\/\d+/)
  const body = page.locator('.smart-vxe .body--wrapper > .vxe-table--body-inner-wrapper')
  await body.waitFor()

  const target = page.locator('.body--wrapper .vxe-body--row').first().locator('td').nth(2)
  await target.click({ button: 'right' })
  const menu = page.locator('.cell-context-menu')
  await menu.waitFor()
  assert.equal(await menu.locator(':scope > .cell-menu-entry').count(), 10)
  assert.equal(await menu.locator('.cell-menu-divider').count(), 5)
  await page.keyboard.press('Escape')
  await target.click({ button: 'right' })
  await menu.getByLabel('向上插入行数').fill('3')
  await menu.getByRole('menuitem', { name: '向上插入', exact: true }).click()
  await page.waitForResponse(response => response.url().includes('/grid'))
  await page.waitForTimeout(500)
  assert.equal(insertRequests[0].direction, 'up')
  assert.equal(insertRequests[0].count, 3)
  await target.click({ button: 'right' })
  await menu.getByLabel('向下插入行数').fill('2')
  await menu.getByLabel('向下插入行数').press('Enter')
  await page.waitForResponse(response => response.url().includes('/grid'))
  await page.waitForTimeout(500)
  assert.equal(insertRequests[1].direction, 'down')
  assert.equal(insertRequests[1].count, 2)
  await target.click({ button: 'right' })
  await menu.getByLabel('向上插入行数').fill('0')
  await menu.getByRole('menuitem', { name: '向上插入', exact: true }).click()
  assert.equal(insertRequests.length, 2)
  await page.keyboard.press('Escape')
  await target.click({ button: 'right' })
  await menu.getByRole('menuitem').nth(3).hover()
  await menu.locator('.cell-menu-sub').waitFor()
  assert.equal(await menu.locator('.cell-menu-sub button').count(), 3)
  await page.screenshot({ path: 'test-results/cell-context-menu.png' })
  await page.keyboard.press('Escape')
  assert.equal(await menu.count(), 0)
  await target.click({ button: 'right' })
  await menu.getByRole('menuitem').first().click()
  await page.locator('.rd-panel').waitFor()
  await page.waitForTimeout(700)
  await target.click({ button: 'right' })
  await page.mouse.click(5, 5)
  assert.equal(await menu.count(), 0)
  await page.mouse.click(900, 850, { button: 'right' })
  await menu.waitFor()
  const bounds = await menu.boundingBox()
  assert.ok(bounds.x + bounds.width <= 1592 && bounds.y + bounds.height <= 992)
  await page.keyboard.press('Escape')
  assert.deepEqual(errors, [])
  console.log('PASS context menu sections, submenu, dismissal, expand record; no data writes')
} finally { await browser.close() }
