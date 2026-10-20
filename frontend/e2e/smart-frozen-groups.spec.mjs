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

  const fields = ['a', 'b', 'c', 'd'].map((field_name, i) => ({ id: 9000 + i, field_name, label: `Column ${field_name}`, field_type: 'text', data_type: 'varchar', options: {} }))
  let frozen = 'b'
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch()
    const meta = await response.json()
    await route.fulfill({ response, json: { ...meta, fields } })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/column-groups$/, route => route.fulfill({ json: {
    groups: [{ id: 700, name: 'Fixture group', field_names: ['b', 'c'] }],
  } }))
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    data.fields = fields
    data.items = [{ id: 901, a: 'value-a', b: 'value-b', c: 'value-c', d: 'value-d' }]
    data.total = 1
    data.grouped = false
    data.view.config = { ...data.view.config, fieldVisibility: {}, fieldOrder: ['a', 'b', 'c', 'd'], frozenFieldId: frozen, colWidths: { a: 180, b: 180, c: 180, d: 1200 }, groups: [] }
    await route.fulfill({ response, json: data })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.locator('.smart-home .t-name').first().click()
  await page.waitForURL(/\/smart\/table\/\d+/)
  for (const boundary of ['b', 'c', 'a', null]) {
    frozen = boundary
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.smart-vxe .vxe-body--row').first().waitFor()
    const group = page.locator('.cg-name').filter({ hasText: 'Fixture group' })
    const groupBox = await group.first().boundingBox()
    await page.mouse.click(groupBox.x + groupBox.width / 2, groupBox.y + groupBox.height / 2)
    await page.waitForFunction(() => document.querySelectorAll('td.col-selected').length >= 2)
    const selected = await page.locator('td.col-selected').allTextContents()
    assert.ok(selected.every(text => ['value-b', 'value-c'].includes(text.trim())), JSON.stringify(selected))
    assert.ok(selected.some(text => text.trim() === 'value-b'))
    assert.ok(selected.some(text => text.trim() === 'value-c'))
    const alignment = await page.evaluate(() => {
      const visible = el => getComputedStyle(el).visibility !== 'hidden' && el.getBoundingClientRect().width > 0
      return ['a', 'b', 'c'].every(name => {
        const header = [...document.querySelectorAll('th')].find(el => visible(el) && el.textContent.trim().endsWith(`Column ${name}`))
        const cell = [...document.querySelectorAll('td')].find(el => visible(el) && el.textContent.trim() === `value-${name}`)
        return header && cell && Math.abs(header.getBoundingClientRect().left - cell.getBoundingClientRect().left) < 2
      })
    })
    assert.ok(alignment, `Header/body alignment with frozen ${boundary}`)
    const utilityAlignment = await page.locator('th.th-utility').evaluateAll(cells => cells.filter(el => getComputedStyle(el).visibility !== 'hidden').map(el => {
      const content = el.querySelector('.vxe-cell--checkbox') || el.querySelector('.vxe-cell--title')
      const rect = content.getBoundingClientRect()
      const title = [...document.querySelectorAll('th.th-span .field-name')].find(node => getComputedStyle(node).visibility !== 'hidden')
      const titleRect = title.getBoundingClientRect()
      return Math.abs(rect.top + rect.height / 2 - titleRect.top - titleRect.height / 2)
    }))
    assert.ok(utilityAlignment.every(delta => delta < 2), JSON.stringify(utilityAlignment))
    assert.ok(await page.locator('th.th-col-selected.sel-t').evaluateAll(els => els
      .filter(el => getComputedStyle(el).visibility !== 'hidden')
      .every(el => {
        const line = getComputedStyle(el, '::after')
        return line.height === '1px' && line.top === (el.parentElement.matches(':first-child') ? '1px' : '0px') && line.backgroundColor !== 'rgba(0, 0, 0, 0)'
      })))
  }
  assert.deepEqual(errors, [])
  console.log('PASS grouped selection and header/body alignment across partial, full, preceding and cleared freezes; no data written')
} finally {
  await browser.close()
}
