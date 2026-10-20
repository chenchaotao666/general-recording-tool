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
  await page.locator('.pager').waitFor()
  for (const height of [1000, 760]) {
    await page.setViewportSize({ width: 1600, height })
    await page.waitForFunction(() => {
      const pager = document.querySelector('.pager').getBoundingClientRect()
      const area = document.querySelector('.st-main').getBoundingClientRect()
      return pager.height === 32 && Math.abs(pager.bottom - area.bottom) < 1
    })
  }
  assert.deepEqual(errors, [])
  console.log('PASS compact pagination fills available height after viewport resize; no data written')

} finally { await browser.close() }
