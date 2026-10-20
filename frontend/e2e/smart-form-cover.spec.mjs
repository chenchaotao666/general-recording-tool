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

  let fixtureView
  let fixtureFields
  const saves = []
  await page.route(/\/api\/smart\/tables\/\d+\/fields\/question_\d+\/deps$/, route => route.fulfill({ json: { deps: [] } }))
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch()
    const meta = await response.json()
    const template = meta.fields.find(f => f.field_type === 'text')
    fixtureFields = Array.from({ length: 3 }, (_, i) => ({ ...template, id: 9000 + i, field_name: `question_${i}`, label: `Question ${i + 1}` }))
    meta.fields = fixtureFields
    await route.fulfill({ response, json: meta })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    data.view.type = 'form'
    data.view.config = { form: { title: 'Form layout', items: fixtureFields.map(f => ({ fieldId: f.field_name })) } }
    fixtureView = data.view
    await route.fulfill({ response, json: data })
  })
  await page.route(/\/api\/smart\/views\/\d+$/, async route => {
    if (route.request().method() !== 'PATCH') return route.continue()
    const data = route.request().postDataJSON()
    // Match the backend: incomplete conditions without a field are discarded on save.
    for (const item of data.config.form.items) {
      if (item.visibility) {
        const conditions = item.visibility.conditions.filter(c => fixtureFields.some(f => f.field_name === c.fieldId))
        item.visibility = conditions.length ? { ...item.visibility, conditions } : null
      }
    }
    saves.push(data)
    fixtureView = { ...fixtureView, config: data.config }
    await route.fulfill({ json: { view: fixtureView } })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '添加封面', exact: true }).click()
  const picker = page.getByRole('dialog', { name: '选择封面' })
  await picker.waitFor()
  assert.equal(await picker.locator('.cover-option').count(), 8)
  await picker.getByRole('button', { name: '沙丘', exact: true }).click()
  await picker.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal(await page.locator('.fv-cover-img').count(), 0, 'Cancel leaves the cover unchanged')
  await page.getByRole('button', { name: '添加封面', exact: true }).click()
  assert.equal(await picker.getByRole('button', { name: '不使用封面' }).getAttribute('aria-pressed'), 'true')
  await picker.getByRole('button', { name: '沙丘', exact: true }).click()
  await page.screenshot({ path: 'test-results/form-cover-picker.png' })
  await picker.getByRole('button', { name: '确定', exact: true }).click()
  await page.waitForTimeout(550)
  assert.equal(saves.at(-1).config.form.cover, 'preset:desert')
  await page.locator('.fv-cover-img').evaluate(img => img.decode())
  const cover = await page.locator('.fv-cover-img').boundingBox()
  const paper = await page.locator('.fv-paper').boundingBox()
  assert.equal(cover.height, 170)
  assert.equal(cover.y + cover.height - paper.y, 44)
  await page.screenshot({ path: 'test-results/form-cover-editor.png' })
  await page.getByRole('button', { name: '封面设置' }).click()
  await page.getByRole('button', { name: '更换封面', exact: true }).click()
  assert.equal(await picker.getByRole('button', { name: '沙丘', exact: true }).getAttribute('aria-pressed'), 'true')
  await picker.getByRole('button', { name: '取消', exact: true }).click()
  await page.locator('.fv-tab').filter({ hasText: '填写表单' }).click()
  const fillCover = await page.locator('.ff-cover').boundingBox()
  const fillPaper = await page.locator('.ff-paper').boundingBox()
  assert.equal(fillCover.y + fillCover.height - fillPaper.y, 44)
  const submit = await page.locator('.ff-submit').boundingBox()
  assert.equal(submit.width, 160)
  assert.ok(Math.abs(submit.x + submit.width / 2 - fillPaper.x - fillPaper.width / 2) < 1)
  await page.screenshot({ path: 'test-results/form-cover-fill.png' })
  await page.locator('.fv-tab').filter({ hasText: '编辑表单' }).click()
  await page.getByRole('button', { name: '封面设置' }).click()
  await page.getByRole('button', { name: '移除封面', exact: true }).click()
  assert.equal(await page.locator('.fv-cover-img').count(), 0)
  await page.locator('[data-smart-tip="撤销"]').click()
  assert.equal(await page.locator('.fv-cover-img').count(), 1)
  await page.getByRole('button', { name: '封面设置' }).click()
  await page.getByRole('button', { name: '更换封面', exact: true }).click()
  await picker.getByRole('button', { name: '不使用封面' }).click()
  await picker.getByRole('button', { name: '确定', exact: true }).click()
  await page.waitForTimeout(550)
  assert.equal(saves.at(-1).config.form.cover, null)
  assert.equal(await page.locator('.fv-cover-img').count(), 0)

  // Public pages resolve the same preset without a private image request.
  await page.route('**/api/smart-public/forms/cover-fixture', route => route.fulfill({ json: {
    title: '收集表单', cover: 'preset:desert', items: [], submit: {},
  } }))
  await page.goto(`${base}/sf/cover-fixture`, { waitUntil: 'networkidle' })
  await page.locator('.ff-cover img').evaluate(img => img.decode())
  assert.ok((await page.locator('.ff-cover img').getAttribute('src')).endsWith('/desert.jpg'))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'test-results/form-cover-mobile.png' })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  assert.deepEqual(errors, [])
  console.log('PASS cover picker, cancel/confirm, persistence, change/remove/undo, fill layout and public mobile form; writes mocked')
} finally { await browser.close() }
