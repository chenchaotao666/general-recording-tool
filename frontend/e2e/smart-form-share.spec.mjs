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
  let link = null
  let failSave = false
  let failLoad = false
  const shareWrites = []
  await page.route(/\/api\/smart\/views\/\d+\/share-link$/, async route => {
    const method = route.request().method()
    if ((method === 'POST' && failSave) || (method === 'GET' && failLoad)) {
      return route.fulfill({ status: 500, json: { detail: '测试失败' } })
    }
    if (method === 'POST') {
      const data = route.request().postDataJSON()
      shareWrites.push(data)
      link = { id: 1, token: 'share-fixture', has_password: !!data.password }
    }
    if (method === 'DELETE') link = null
    await route.fulfill({ json: { link } })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  const panel = page.locator('.form-share-pop:visible')
  const toggle = panel.getByRole('switch', { name: '启用表单链接' })
  await panel.waitFor()
  await page.waitForTimeout(350)
  assert.equal(await panel.locator('.fs-body').count(), 0)
  await page.screenshot({ animations: 'disabled', path: 'test-results/form-share-disabled.png' })
  await panel.locator('.el-switch').click()
  await page.waitForTimeout(150)
  assert.equal(await toggle.getAttribute('aria-checked'), 'true')
  await page.screenshot({ animations: 'disabled', path: 'test-results/form-share.png' })
  await panel.locator('.el-select').click()
  await page.getByRole('option', { name: '凭密码访问' }).click()
  assert.ok(await panel.getByRole('button', { name: '复制链接' }).isDisabled())
  await panel.getByPlaceholder('输入访问密码（至少 4 位）').fill('abc')
  assert.ok(await panel.getByRole('button', { name: '保存', exact: true }).isDisabled())
  await panel.getByPlaceholder('输入访问密码（至少 4 位）').fill('safe-pass')
  failSave = true
  await panel.getByRole('button', { name: '保存', exact: true }).click()
  await page.waitForTimeout(150)
  assert.equal(link.has_password, false)
  assert.equal(await panel.getByPlaceholder('输入访问密码（至少 4 位）').inputValue(), 'safe-pass')
  failSave = false
  await panel.getByRole('button', { name: '保存', exact: true }).click()
  await page.waitForTimeout(150)
  assert.equal(shareWrites.at(-1).password, 'safe-pass')
  assert.ok(link.has_password)
  await page.screenshot({ animations: 'disabled', path: 'test-results/form-share-password.png' })
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await page.waitForTimeout(300)
  await panel.getByText('已启用密码保护，留空保留原密码').waitFor()
  assert.equal(await panel.getByPlaceholder('输入访问密码（至少 4 位）').inputValue(), '')
  // Clipboard fallback and QR generation do not send messages to anyone.
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
    writeText: async () => { throw new Error('Denied') },
  } }))
  await panel.getByRole('button', { name: '复制链接' }).click()
  const copyDialog = page.getByRole('dialog', { name: '复制表单链接' })
  await copyDialog.waitFor()
  assert.equal(await copyDialog.getByRole('textbox').inputValue(), `${base}/sf/share-fixture`)
  await copyDialog.locator('.el-dialog__headerbtn').click()
  await copyDialog.waitFor({ state: 'hidden' })
  if (!(await panel.isVisible())) await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await panel.getByRole('button', { name: '表单二维码', exact: true }).click()
  const qr = page.getByRole('dialog', { name: '获取二维码' })
  await qr.waitFor()
  await qr.locator('img').evaluate(img => img.decode())
  assert.ok((await qr.locator('img').getAttribute('src')).startsWith('data:image/png;base64,'))
  await qr.getByText('使用微信或企业微信扫码填写').waitFor()
  await qr.getByText('此表单需输入访问密码').waitFor()
  assert.equal(await qr.locator('h3').innerText(), 'Form layout')
  await page.screenshot({ animations: 'disabled', path: 'test-results/form-share-qr.png' })
  const download = page.waitForEvent('download')
  await qr.getByRole('button', { name: '保存二维码' }).click()
  const saved = await download
  assert.equal(saved.suggestedFilename(), '表单二维码.png')
  await saved.saveAs('test-results/form-share-card.png')
  await qr.locator('.el-dialog__headerbtn').click()
  await qr.waitFor({ state: 'hidden' })
  if (!(await panel.isVisible())) await page.getByRole('button', { name: '分享表单', exact: true }).click()
  assert.equal(await panel.getByRole('button', { name: '分享链接', exact: true }).count(), 0)
  await panel.getByRole('button', { name: '分享到微信', exact: true }).click()
  const wechat = page.getByRole('dialog', { name: '分享到微信' })
  await wechat.waitFor()
  await wechat.getByText('请复制链接并前往微信分享').waitFor()
  await page.screenshot({ animations: 'disabled', path: 'test-results/form-share-wechat.png' })
  // Keep external apps closed: exercise denied clipboard and its manual-copy fallback.
  await wechat.getByRole('button', { name: '复制链接并打开微信', exact: true }).click()
  await wechat.getByText('自动复制失败，请手动复制下方链接后打开微信。').waitFor()
  assert.equal(await wechat.getByRole('textbox', { name: '微信分享链接' }).inputValue(), `${base}/sf/share-fixture`)
  await wechat.getByRole('button', { name: '取消', exact: true }).click()
  await wechat.waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await panel.locator('.el-select').click()
  await page.getByRole('option', { name: '任何人（无需登录）' }).click()
  await page.waitForTimeout(150)
  assert.equal(link.has_password, false)
  assert.equal(shareWrites.at(-1).password, '')
  await panel.locator('.el-switch').click()
  await page.waitForTimeout(150)
  assert.equal(link, null)
  assert.equal(await panel.locator('.fs-body').count(), 0)
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await panel.waitFor({ state: 'hidden' })
  failLoad = true
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await page.waitForTimeout(300)
  await panel.getByText('链接加载失败').waitFor()
  assert.equal(await toggle.getAttribute('aria-disabled'), 'true')
  failLoad = false
  await panel.getByRole('button', { name: '重试', exact: true }).click()
  await page.waitForTimeout(150)
  assert.equal(await panel.locator('.fs-error').count(), 0)
  assert.deepEqual(errors, [])
  console.log('PASS form share enable/disable, password persistence/failure, clipboard fallback, QR/save and load retry; writes mocked')
} finally { await browser.close() }
