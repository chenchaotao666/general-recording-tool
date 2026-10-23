import { chromium } from 'playwright'
import assert from 'node:assert/strict'

const base = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  page.setDefaultTimeout(10000)
  const login = await (await page.request.post(`${base}/api/auth/login`, { data: {
    username: process.env.E2E_USER || 'admin', password: process.env.E2E_PASS || 'admin123',
  } })).json()
  assert.ok(login.token, 'Login failed')
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem('grt_token', token)
    localStorage.setItem('grt_user', JSON.stringify(user))
    localStorage.setItem('grt_tenant_id', String(user.tenant?.id || user.tenant_id || ''))
    sessionStorage.setItem('grt_tenant_picked', '1')
  }, login)
  let fields
  const requests = []
  let runState = { status: 'error', error: '本月 AI 调用次数已用完，请升级套餐' }
  let output = ''
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route(/\/api\/tables\/\d+$/, async route => {
    const response = await route.fetch()
    const meta = await response.json()
    const template = meta.fields.find(field => field.field_type === 'text')
    assert.ok(template, 'Need an existing text field')
    fields = [
      { ...template, field_name: 'ai_retry_test', field_type: 'ai', label: 'AI retry', options: { outputType: 'text', inputFields: ['source'], prompt: 'Summarize' } },
      { ...template, id: 99001, field_name: 'source', label: 'Source' },
    ]
    meta.fields = fields
    await route.fulfill({ response, json: meta })
  })
  await page.route(/\/api\/smart\/tables\/\d+\/grid(?:\?|$)/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    data.fields = fields
    data.items = [{ id: 99001, ai_retry_test: output, source: 'Test input', ...(runState ? { __ai: { ai_retry_test: runState } } : {}) }]
    data.total = 1
    data.grouped = false
    data.view.config = { ...data.view.config, hiddenFields: [], fieldVisibility: {}, fieldOrder: ['ai_retry_test', 'source'], frozenFields: [], groups: [] }
    await route.fulfill({ response, json: data })
  })
  await page.route(/\/api\/smart\/.*ai.*$/, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    requests.push({ url: route.request().url(), body: route.request().postDataJSON() })
    runState = { status: 'pending', error: null }
    await route.fulfill({ json: { queued: 1 } })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  const cell = page.locator('.body--wrapper .vxe-body--row').first().locator('td').nth(1)
  await cell.click()
  await page.locator('.arb-main').waitFor()
  assert.match(await cell.innerText(), /本月 AI 调用次数已用完/, 'Selecting an AI cell must keep its failure visible')
  await page.locator('.arb-main').click()
  await page.waitForTimeout(500)
  assert.equal(requests.length, 1, 'A single click must enqueue one generation request')
  assert.deepEqual(requests[0].body, { record_ids: [99001] })
  await cell.getByText('正在生成…', { exact: true }).waitFor()
  runState = { status: 'error', error: '模型服务暂时不可用' }
  await cell.getByText('生成失败 · 模型服务暂时不可用', { exact: true }).waitFor()
  await page.locator('.arb-main').click()
  await cell.getByText('正在生成…', { exact: true }).waitFor()
  runState = null
  output = 'Regenerated result'
  await page.locator('.preview-text').getByText(output, { exact: true }).waitFor()
  assert.equal(requests.length, 2)
  assert.deepEqual(requests[1].body, { record_ids: [99001] })
  assert.deepEqual(errors, [])
  console.log('PASS: selected AI cell shows failure, retries its own row, displays progress and refreshed result.')
} finally {
  await browser.close()
}
