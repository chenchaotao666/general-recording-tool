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
  let searchRequests = 0
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch()
    const meta = await response.json()
    field = meta.fields.find(f => f.field_type === 'text')?.field_name
    assert.ok(field, 'Need an existing table with a text field')
    await route.fulfill({ response })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    data.items = [901, 902, 903].map(id => ({ id, [field]: `search-fixture-${id}` }))
    data.total = 3
    data.grouped = false
    data.view.config = { ...data.view.config, hiddenFields: [], fieldOrder: [field], groups: [] }
    await route.fulfill({ response, json: data })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/search-replace$/, async route => {
    searchRequests++
    assert.equal(route.request().postDataJSON().replace, undefined)
    await route.fulfill({ json: { matches: [903, 901, 902].map(recordId => ({ recordId, field, fieldType: 'text', value: `search-fixture-${recordId}`, replaceable: true })) } })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.locator('.smart-home .t-name').first().click()
  await page.waitForURL(/\/smart\/table\/\d+/)
  await page.locator('.smart-vxe .vxe-body--row').first().waitFor()
  await page.locator('button[title="\u67e5\u627e\u66ff\u6362"]').click()
  const dialog = page.locator('.el-dialog.smart-find-dialog')
  await dialog.waitFor()
  const head = dialog.locator('.fr-head')
  await head.click({ trial: true })
  const before = await dialog.boundingBox()
  const handle = await head.boundingBox()
  await page.mouse.move(handle.x + 40, handle.y + 12)
  await page.mouse.down()
  await page.mouse.move(handle.x - 100, handle.y + 92, { steps: 8 })
  await page.mouse.up()
  const after = await dialog.boundingBox()
  assert.ok(Math.abs(after.x - before.x + 140) < 2, `Drag x: ${before.x} -> ${after.x}`)
  assert.ok(Math.abs(after.y - before.y - 80) < 2, `Drag y: ${before.y} -> ${after.y}`)
  await dialog.locator('.fr-expand').click()
  await dialog.locator('.fr-find-input').fill('search-fixture')
  await dialog.locator('.fr-primary').click()
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('901'))
  assert.equal(await dialog.locator('.fr-count').innerText(), '2/3')
  await dialog.locator('.fr-primary').click()
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('902'))
  await dialog.locator('.fr-primary').click()
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('903'))
  assert.equal(searchRequests, 1)
  assert.deepEqual(errors, [])
  console.log('PASS real Element Plus dialog drag, current-page first match, repeated find, wraparound; no data written')
} finally {
  await browser.close()
}
