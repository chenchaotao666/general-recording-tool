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
    data.items = [901, 902, 903].map(id => ({ id, [field]: `search-fixture-${id}` }))
    data.fields = fixtureFields
    data.total = 3
    data.grouped = false
    data.view.config = { ...data.view.config, hiddenFields: [], fieldVisibility: {}, fieldOrder: fixtureFields.map(f => f.field_name), frozenFields: [], groups: [] }
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
  await page.locator('button[data-smart-tip="\u67e5\u627e\u66ff\u6362"]').click()
  const dialog = page.locator('.el-dialog.smart-find-dialog')
  await dialog.waitFor()
  const head = dialog.locator('.fr-head')
  await head.click({ trial: true })
  const before = await dialog.boundingBox()
  const handle = await head.boundingBox()
  await page.mouse.move(handle.x + 40, handle.y + 3)
  await page.mouse.down()
  await page.mouse.move(handle.x - 100, handle.y + 83, { steps: 8 })
  await page.mouse.up()
  const after = await dialog.boundingBox()
  assert.ok(Math.abs(after.x - before.x + 140) < 2, `Drag x: ${before.x} -> ${after.x}`)
  assert.ok(Math.abs(after.y - before.y - 80) < 2, `Drag y: ${before.y} -> ${after.y}`)
  await dialog.locator('.fr-expand').click()
  await dialog.locator('.fr-find-input').fill('search-fixture')
  await dialog.locator('.fr-find-input').press('Enter')
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('901'))
  assert.ok(await dialog.locator('.fr-find-input').evaluate(el => el === document.activeElement))
  assert.equal(await dialog.locator('.fr-count').innerText(), '1/3')
  await page.waitForFunction(() => {
    const cells = [...document.querySelectorAll('.cell-search-active')]
    return cells.some(cell => {
      if (getComputedStyle(cell).visibility === 'hidden') return false
      const rect = cell.getBoundingClientRect()
      const grid = cell.closest('.smart-vxe').getBoundingClientRect()
      return rect.width > 0 && rect.left >= grid.left + 88 && rect.right <= grid.right + 1
    })
  })
  const highlightedNumbers = page.locator('.col-no.cell-search-match')
  assert.ok(await highlightedNumbers.count() >= 3)
  assert.equal(await highlightedNumbers.first().evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 252, 235)')
  await dialog.locator('[aria-label="\u4e0b\u4e00\u4e2a"]').click()
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('902'))
  assert.equal(await dialog.locator('.fr-count').innerText(), '2/3')
  await dialog.locator('.fr-find-input').focus()
  await dialog.locator('.fr-find-input').press('Enter')
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('903'))
  assert.ok(await dialog.locator('.fr-find-input').evaluate(el => el === document.activeElement))
  await dialog.locator('.fr-primary').click()
  await page.waitForFunction(() => document.querySelector('.cell-search-active')?.textContent.includes('901'))
  assert.equal(searchRequests, 1)
  assert.deepEqual(errors, [])
  console.log('PASS real Element Plus dialog drag, current-page first match, repeated find, wraparound, row number highlights, off-screen virtual column scrolling; no data written')
} finally {
  await browser.close()
}
