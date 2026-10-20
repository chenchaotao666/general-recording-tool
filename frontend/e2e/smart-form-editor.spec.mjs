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
  const cards = page.locator('.fv-q')
  await cards.first().waitFor()
  assert.equal(await cards.count(), 3)
  const first = await cards.nth(0).boundingBox()
  const second = await cards.nth(1).boundingBox()
  assert.ok(second.y - first.y - first.height >= 4)
  await cards.first().click()
  assert.equal(await cards.first().locator('[aria-disabled="true"]').count(), 1)
  await cards.first().locator('[aria-disabled="true"]').hover()
  await page.getByRole('tooltip', { name: '表单的首个问题不支持设置显示条件' }).waitFor()
  assert.equal(await page.getByRole('tooltip', { name: '表单的首个问题不支持设置显示条件' })
    .evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)')
  await page.screenshot({ path: 'test-results/form-first-question.png' })
  await cards.nth(1).click()
  await cards.nth(1).locator('.fv-attr-btn').first().click()
  const pop = page.locator('.fv-condition-pop:visible')
  await pop.waitFor()
  await pop.locator('.fv-vis-add').click()
  await pop.locator('.pcr').waitFor()
  await page.waitForTimeout(550)
  assert.ok(saves.length)
  assert.equal(saves.at(-1).config.form.items[1].visibility.conditions.length, 1)
  assert.equal(await pop.locator('.pcr').count(), 1)
  assert.equal(saves.at(-1).config.form.items[1].visibility.conditions[0].fieldId, 'question_0')
  assert.equal(saves.at(-1).config.form.items[1].visibility.conditions[0].operator, 'isNotEmpty')
  await pop.locator('.fv-vis-add').click()
  await page.waitForTimeout(550)
  assert.equal(await pop.locator('.pcr').count(), 2)
  await page.screenshot({ path: 'test-results/form-display-condition.png' })
  const editButton = cards.nth(1).getByRole('button', { name: '编辑字段', exact: true })
  const editBounds = await editButton.boundingBox()
  await editButton.click()
  await page.locator('.st-fcd').waitFor()
  await page.waitForTimeout(350)
  const editorBounds = await page.locator('.st-fcd').boundingBox()
  assert.ok(editorBounds.x >= 12 && editorBounds.x + editorBounds.width <= 1588)
  assert.ok(editorBounds.y >= 12 && editorBounds.y + editorBounds.height <= 988)
  assert.ok(Math.min(Math.abs(editorBounds.y - editBounds.y - editBounds.height),
    Math.abs(editBounds.y - editorBounds.y - editorBounds.height)) <= 8, 'Editor stays beside the edit button')
  await page.setViewportSize({ width: 900, height: 600 })
  await page.waitForTimeout(100)
  const compactBounds = await page.locator('.st-fcd').boundingBox()
  assert.ok(compactBounds.x >= 12 && compactBounds.x + compactBounds.width <= 888)
  assert.ok(compactBounds.y >= 12 && compactBounds.y + compactBounds.height <= 588)
  await page.screenshot({ path: 'test-results/form-editor-anchored.png' })
  await page.setViewportSize({ width: 1600, height: 1000 })
  assert.equal(await page.locator('.fcd-name').inputValue(), 'Question 2')
  await page.locator('.st-fcd').getByRole('button', { name: '取消', exact: true }).click()
  await cards.nth(1).getByRole('button', { name: '删除字段', exact: true }).click()
  await page.locator('.el-message-box').waitFor()
  assert.ok((await page.locator('.el-message-box').innerText()).includes('存量数据将一并清除'))
  await page.locator('.el-message-box').getByRole('button', { name: '取消', exact: true }).click()
  assert.equal(await cards.count(), 3)
  await page.getByRole('button', { name: '全部移出', exact: true }).click()
  assert.equal(await cards.count(), 0)
  await page.locator('.fv-avail[data-field-id="question_0"]').dragTo(page.locator('.fv-paper'), {
    targetPosition: { x: 100, y: 180 },
  })
  await page.locator('.fv-q.active[data-field-id="question_0"]').waitFor()
  assert.equal(await cards.count(), 1)
  await page.locator('.fv-avail[data-field-id="question_1"]').dragTo(cards.first(), {
    targetPosition: { x: 100, y: 5 },
  })
  assert.deepEqual(await cards.evaluateAll(els => els.map(el => el.dataset.fieldId)), ['question_1', 'question_0'])
  await page.locator('.fv-q.active[data-field-id="question_1"]').waitFor()
  await page.getByRole('button', { name: '全部添加', exact: true }).click()
  assert.equal(await cards.count(), 3)
  assert.ok(await page.getByRole('button', { name: '全部添加', exact: true }).isDisabled())
  await page.locator('[data-smart-tip="撤销"]').click()
  assert.equal(await cards.count(), 2)
  await page.locator('[data-smart-tip="重做"]').click()
  assert.equal(await cards.count(), 3)
  const last = page.locator('.fv-q[data-field-id="question_2"]')
  const lastBox = await last.boundingBox()
  await page.locator('.fv-q[data-field-id="question_1"] .fv-drag').dragTo(last, {
    targetPosition: { x: 100, y: lastBox.height - 5 },
  })
  assert.deepEqual(await cards.evaluateAll(els => els.map(el => el.dataset.fieldId)), ['question_0', 'question_2', 'question_1'])
  await page.locator('.fv-q.active[data-field-id="question_1"]').waitFor()
  await page.waitForTimeout(550)
  assert.deepEqual(saves.at(-1).config.form.items.map(it => it.fieldId), ['question_0', 'question_2', 'question_1'])
  await page.screenshot({ path: 'test-results/form-drag-added.png' })
  await page.setViewportSize({ width: 1600, height: 650 })
  await cards.first().locator('.fv-drag').scrollIntoViewIfNeeded()
  const handle = await cards.first().locator('.fv-drag').boundingBox()
  const canvas = page.locator('.fv-canvas')
  const canvasBox = await canvas.boundingBox()
  const beforeScroll = await canvas.evaluate(el => el.scrollTop)
  await page.mouse.move(handle.x + 6, handle.y + 6)
  await page.mouse.down()
  await page.mouse.move(handle.x + 20, handle.y + 20, { steps: 4 })
  await page.mouse.move(canvasBox.x + 160, canvasBox.y + canvasBox.height - 12, { steps: 8 })
  await page.mouse.move(canvasBox.x + 161, canvasBox.y + canvasBox.height - 10)
  await page.waitForTimeout(250)
  assert.ok(await canvas.evaluate(el => el.scrollTop) > beforeScroll, 'Dragging near the bottom scrolls the canvas')
  await page.screenshot({ path: 'test-results/form-drag-placeholder.png' })
  await page.keyboard.press('Escape')
  await page.mouse.up()
  assert.equal(await page.locator('.fv-drop-placeholder').count(), 0)
  assert.deepEqual(await cards.evaluateAll(els => els.map(el => el.dataset.fieldId)), ['question_0', 'question_2', 'question_1'])
  assert.deepEqual(errors, [])
  console.log('PASS form conditions, drag to empty/before/after, add all, undo/redo and persisted order; writes mocked')
} finally { await browser.close() }
