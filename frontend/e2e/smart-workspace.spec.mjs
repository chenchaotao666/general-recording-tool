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

  let sheets
  const loaded = []
  page.on('request', req => { if (/\/smart\/tables\/\d+\/grid/.test(req.url())) loaded.push(req.url()) })
  await page.route(/\/api\/smart\/docs\/\d+\/tree$/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    sheets = data.entries.filter(e => e.type === 'sheet').slice(0, 2)
    assert.equal(sheets.length, 2, 'Need two existing sheets for read-only navigation checks')
    data.entries = [{ id: 999991, parent_id: null, name: 'Workspace folder', type: 'folder' },
      ...sheets.map((e, i) => ({ ...e, name: `Workspace sheet ${i + 1}`, parent_id: 999991 }))]
    await route.fulfill({ response, json: data })
  })
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.waitForURL(/\/smart\/table\/\d+/)
  await page.locator('.smart-content .smart-vxe').waitFor()
  assert.ok(await page.locator('.smart-home .nav').isVisible())
  await Promise.all([
    page.waitForResponse(res => res.url().includes(`/tables/${sheets[1].ref_table_id}/grid`)),
    page.locator('.t-name').filter({ hasText: 'Workspace sheet 2' }).click(),
  ])
  await page.waitForURL(`**/smart/table/${sheets[1].ref_table_id}`)
  await page.locator('.smart-content .smart-vxe').waitFor()
  assert.ok(loaded.some(url => url.includes(`/tables/${sheets[1].ref_table_id}/grid`)))
  assert.ok((await page.locator('.el-tree-node.is-current > .el-tree-node__content').innerText()).includes('Workspace sheet 2'))
  await page.locator('.side-top input').fill('sheet 2')
  assert.equal(await page.locator('.t-name').filter({ hasText: 'Workspace folder' }).count(), 1)
  assert.equal(await page.locator('.t-name').filter({ hasText: 'Workspace sheet 1' }).count(), 0)
  await page.locator('.side-top input').fill('')
  const before = await page.locator('.smart-home .nav').boundingBox()
  const handle = await page.locator('.side-resizer').boundingBox()
  await page.mouse.move(handle.x + 5, handle.y + 80)
  await page.mouse.down()
  await page.mouse.move(handle.x + 65, handle.y + 80)
  await page.mouse.up()
  assert.equal(Math.round((await page.locator('.smart-home .nav').boundingBox()).width - before.width), 60)
  await page.locator('.side-top-row .side-fold').first().click()
  assert.equal(await page.locator('.smart-home .nav').isVisible(), false)
  assert.ok(await page.locator('.smart-content .smart-vxe').isVisible())
  await page.locator('.side-expand').click()
  await page.reload({ waitUntil: 'networkidle' })
  await page.locator('.smart-content .smart-vxe').waitFor()
  assert.ok(await page.locator('.smart-home .nav').isVisible())
  await page.goto(`${base}/smart`, { waitUntil: 'networkidle' })
  await page.waitForURL(`**/smart/table/${sheets[1].ref_table_id}`)
  await page.locator('.smart-content .smart-vxe').waitFor()
  await page.locator('.smart-vxe .vxe-body--row').first().hover()
  await page.locator('.st-row-expand').click()
  await page.locator('.rd-panel').waitFor()
  const tabs = await page.locator('.view-tabs').boundingBox()
  const detailTop = await page.locator('.rd-top').boundingBox()
  const tablePanel = await page.locator('.st-panel').boundingBox()
  const detailCard = await page.locator('.rd-card').boundingBox()
  assert.ok(Math.abs(tabs.y - detailTop.y) < 1)
  assert.ok(Math.abs(tablePanel.y - detailCard.y) < 1)
  await page.screenshot({ path: 'frontend/test-results/smart-workspace.png' })
  assert.deepEqual(errors, [])
  console.log('PASS persistent directory, direct sheet opening, sheet switching, nested search, resize, collapse, reload and last-sheet restore; no data written')
} finally { await browser.close() }
