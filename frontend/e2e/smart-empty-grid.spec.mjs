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
  let mode = 'empty'
  let fields
  let created = false
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch()
    const meta = await response.json()
    const template = meta.fields.find(f => f.field_type === 'text')
    fields = Array.from({ length: mode === 'wide' ? 26 : 3 }, (_, i) => ({
      ...template, id: 9000 + i, field_name: `empty_${i}`, label: `Field ${i + 1}`,
    }))
    meta.fields = fields
    await route.fulfill({ response, json: meta })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    data.items = created ? [{ id: 999001, empty_0: 'New record' }] : []
    data.total = data.items.length
    data.grouped = false
    data.aggregations = {}
    data.my_perms = { can_create: mode !== 'readonly', can_edit: mode !== 'readonly', can_delete: mode !== 'readonly' }
    data.view.type = 'grid'
    data.view.config = {
      fieldVisibility: {}, fieldOrder: fields.map(f => f.field_name),
      frozenFieldId: mode === 'wide' ? fields[0].field_name : null,
      filters: { conditions: mode === 'filtered' ? [{ fieldId: fields[0].field_name, operator: 'isNotEmpty' }] : [] },
    }
    await route.fulfill({ response, json: data })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/records$/, async route => {
    assert.equal(route.request().method(), 'POST')
    created = true
    await route.fulfill({ json: { record: { id: 999001, empty_0: 'New record' } } })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  const grid = page.locator('.smart-vxe')
  const footer = page.locator('.vxe-table--main-wrapper .vxe-table--footer-wrapper')
  await page.locator('.smart-grid.is-empty').waitFor()
  const headerBox = await page.locator('.vxe-table--main-wrapper .vxe-table--header-wrapper').boundingBox()
  const footerBox = await footer.boundingBox()
  assert.ok((await grid.boundingBox()).height < 180)
  assert.ok(footerBox.y > headerBox.y + headerBox.height)
  assert.ok((await grid.boundingBox()).width < 650)
  const message = page.locator('.vxe-table--empty-content:visible')
  const msgBox = await message.boundingBox()
  const bounds = await grid.boundingBox()
  assert.ok(Math.abs(msgBox.x + msgBox.width / 2 - bounds.x - bounds.width / 2) < 3)
  assert.ok(Math.abs(footerBox.x + footerBox.width - headerBox.x - headerBox.width) < 3)
  assert.ok(await page.locator('.col-no:visible').count() > 0)
  assert.equal(await page.locator('.grid-empty:visible').count(), 0)
  assert.equal(Math.round((await footer.locator('.vxe-cell').first().boundingBox()).height), 45)
  assert.equal(await page.locator('.pager').count(), 0)
  await page.screenshot({ animations: 'disabled', path: 'test-results/smart-empty-grid.png' })
  const headerAdd = page.locator('.vxe-table--main-wrapper .th-add-col')
  await headerAdd.locator('.add-col').hover()
  assert.equal(await headerAdd.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(230, 232, 232)')
  assert.equal(await headerAdd.locator('.add-col').evaluate(el => getComputedStyle(el).backgroundColor), 'rgba(0, 0, 0, 0)')
  await headerAdd.click({ position: { x: 12, y: 3 } })
  await page.locator('.afp').waitFor()
  await page.keyboard.press('Escape')
  await footer.locator('.footer-add-btn').hover()
  assert.equal(await footer.locator('.footer-add-cell').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(230, 232, 232)')
  assert.equal(await footer.locator('.footer-add-btn').evaluate(el => getComputedStyle(el).backgroundColor), 'rgba(0, 0, 0, 0)')
  await footer.locator('.footer-add-cell').click({ position: { x: 3, y: 3 } })
  await page.locator('.smart-vxe .vxe-body--row').first().waitFor()
  assert.ok(created)
  assert.equal(await page.locator('.smart-grid.is-empty').count(), 0)
  assert.ok(await page.locator('.col-no:visible').count() > 0)

  const populatedBounds = await grid.boundingBox()
  const populatedFooter = await footer.boundingBox()
  assert.ok(populatedBounds.width < 650, 'Populated tables also stop at the final column')
  assert.ok(Math.abs(populatedFooter.x + populatedFooter.width - populatedBounds.x - populatedBounds.width) < 3)
  await page.screenshot({ animations: 'disabled', path: 'test-results/smart-populated-grid-width.png' })
  await page.locator('.vxe-table--main-wrapper .field-head').nth(1).click()
  const selectedFooter = footer.locator('.tf-col-selected.sel-b')
  await selectedFooter.waitFor()
  assert.deepEqual(await selectedFooter.evaluate(el => {
    const style = getComputedStyle(el, '::after')
    return [style.height, style.bottom, style.backgroundColor]
  }), ['1px', '1px', 'rgb(46, 107, 230)'])
  await page.screenshot({ animations: 'disabled', path: 'test-results/smart-column-bottom-border.png' })

  created = false
  for (mode of ['filtered', 'readonly', 'wide']) {
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.smart-grid.is-empty').waitFor()
    assert.ok((await grid.boundingBox()).height < 180)
    if (mode === 'readonly') assert.equal(await page.locator('.footer-add-btn').count(), 0)
    const bounds = await grid.boundingBox()
    assert.ok(bounds.x + bounds.width <= 1600)
    await page.screenshot({ animations: 'disabled', path: `test-results/smart-empty-${mode}.png` })
  }
  assert.deepEqual(errors, [])
  console.log('PASS empty grid within column width, centered message, add-row transition, filtered/readonly and wide frozen columns; writes mocked')
} finally { await browser.close() }
