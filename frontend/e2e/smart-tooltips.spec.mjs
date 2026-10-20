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
    fixtureFields[0].field_type = 'singleSelect'
    fixtureFields[0].options = { options: [] }
    fixtureFields[1].field_type = 'multiSelect'
    fixtureFields[1].options = { options: [] }
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
  await page.locator('.field-head').first().hover()
  await page.waitForTimeout(350)
  assert.equal(await page.locator('.st-unified-tooltip').count(), 0)

  const trigger = page.locator('button[data-smart-tip="\u67e5\u627e\u66ff\u6362"]')
  await trigger.hover()
  const tip = page.locator('.st-unified-tooltip')
  await tip.waitFor()
  assert.deepEqual(await trigger.evaluate(el => {
    const style = getComputedStyle(el)
    return [style.backgroundColor, style.borderRadius]
  }), ['rgb(230, 232, 232)', '4px'])
  assert.equal(await tip.textContent(), '\u67e5\u627e\u66ff\u6362')
  assert.equal(await trigger.getAttribute('title'), null)
  assert.equal(await tip.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)')
  await page.screenshot({ path: 'test-results/smart-unified-tooltip.png' })
  await page.keyboard.press('Escape')
  assert.equal(await tip.count(), 0)
  await trigger.focus()
  await tip.waitFor()
  await trigger.evaluate(el => el.setAttribute('data-smart-tip', 'Updated tooltip'))
  await page.waitForFunction(() => document.querySelector('.st-unified-tooltip')?.textContent === 'Updated tooltip')
  await page.locator('button[data-smart-tip="Updated tooltip"]').click()
  assert.equal(await tip.count(), 0)
  const nativeTitles = await page.locator('.smart-home [title]').evaluateAll(els => els.map(el => ({ tag: el.tagName, text: el.title })))
  assert.deepEqual(nativeTitles, [])
  await page.locator('.fr-close').hover()
  assert.deepEqual(await page.locator('.fr-close').evaluate(el => {
    const style = getComputedStyle(el)
    return [style.backgroundColor, style.borderRadius]
  }), ['rgb(230, 232, 232)', '4px'])
  await page.locator('.fr-close').click()
  for (const col of [2, 3]) {
    await page.locator('.body--wrapper .vxe-body--row').first().locator('td').nth(col).click()
    const arrow = page.locator('.sel-anchor .chev')
    await arrow.waitFor()
    await arrow.hover()
    await page.waitForTimeout(350)
    assert.equal(await tip.count(), 0)
    assert.equal(await arrow.getAttribute('data-smart-tip'), null)
    assert.deepEqual(await arrow.evaluate(el => {
      const style = getComputedStyle(el)
      return [style.backgroundColor, style.borderRadius]
    }), ['rgb(230, 232, 232)', '4px'])
  }
  assert.deepEqual(errors, [])
  console.log('PASS unified tooltip appearance, keyboard focus, dynamic content, dismissal and no native title attributes')
} finally { await browser.close() }
