import { chromium } from 'playwright'
import assert from 'node:assert/strict'

const base = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 480, height: 360 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/smart/views/99001/share-link', route => route.fulfill({ json: { link: { token: 'fixture', has_password: false } } }))
  await page.goto(base, { waitUntil: 'networkidle' })
  await page.evaluate(async () => {
    const { createApp, h, ref } = await import('/node_modules/.vite/deps/vue.js')
    const { default: ElementPlus, ElConfigProvider } = await import('/node_modules/.vite/deps/element-plus.js')
    const { default: AddField } = await import('/src/components/smart/panels/AddFieldPop.vue')
    const { default: VarMenu } = await import('/src/components/smart/automation/VarMenu.vue')
    const { default: MessageEditor } = await import('/src/components/smart/automation/MessageEditor.vue')
    const { default: FormShare } = await import('/src/components/smart/form/FormShare.vue')
    const root = document.createElement('div')
    root.className = 'st-page'
    root.style.cssText = 'position:fixed;inset:0;background:white;z-index:1000'
    document.body.append(root)
    const mode = ref('add')
    window.__popupMode = mode
    window.__popupPicked = []
    createApp({ setup: () => () => h(ElConfigProvider, { zIndex: 4000 }, { default: () => mode.value === 'add'
      ? h(AddField, { x: 470, y: 350 })
      : mode.value === 'vars' ? h(VarMenu, { x: 460, y: 350, steps: [{ step: 1, name: '查找记录', vars: Array.from({ length: 30 }, (_, i) => ({ key: `field_${i}`, label: `Field ${i}`, var: { key: i } })) }], onPick: value => window.__popupPicked.push(value) })
      : mode.value === 'share' ? h(FormShare, { viewId: 99001, canManage: true, style: 'position:fixed;right:0;bottom:0' })
      : h(MessageEditor, { steps: [], style: 'position:fixed;right:0;bottom:0;width:320px' }) }) }).use(ElementPlus).mount(root)
  })
  async function fits(selector) {
    const el = page.locator(selector)
    await el.waitFor()
    await page.waitForTimeout(150)
    const rect = await el.boundingBox(), view = page.viewportSize()
    assert.ok(rect.x >= 0 && rect.y >= 0 && rect.x + rect.width <= view.width + 1 && rect.y + rect.height <= view.height + 1, `${selector}: ${JSON.stringify(rect)}`)
  }
  await fits('.afp')
  await page.setViewportSize({ width: 360, height: 280 })
  await fits('.afp')
  await page.evaluate(() => { window.__popupMode.value = 'vars' })
  await fits('.vm')
  const trigger = await page.locator('.vm > .vm-item').filter({ hasText: '第1步' }).boundingBox()
  await page.mouse.move(trigger.x + 10, trigger.y + 10)
  await fits('.vm-sub-fields')
  const last = page.locator('.vm-sub-fields').getByText('Field 29', { exact: true })
  await last.scrollIntoViewIfNeeded()
  await last.click()
  assert.deepEqual(await page.evaluate(() => window.__popupPicked), [{ key: 29 }])
  await page.evaluate(() => { window.__popupMode.value = 'message' })
  await page.getByText('添加表情', { exact: true }).click()
  await fits('.me-emoji')
  const emoji = page.locator('.me-e').first()
  const point = await emoji.boundingBox()
  assert.equal(await page.evaluate(({ x, y }) => !!document.elementFromPoint(x, y)?.closest('.me-emoji'), { x: point.x + 5, y: point.y + 5 }), true)
  await emoji.click()
  assert.ok((await page.locator('.me-body').textContent()).includes('😀'))
  await page.evaluate(() => { window.__popupMode.value = 'share' })
  await page.getByRole('button', { name: '分享表单', exact: true }).click()
  await fits('.form-share-pop')
  await page.locator('.form-share-pop .el-select__wrapper').click()
  await fits('.el-select__popper:visible')
  await page.getByText('凭密码访问', { exact: true }).click()
  await page.getByPlaceholder('输入访问密码（至少 4 位）').waitFor()
  assert.equal(await page.locator('.form-share-pop').isVisible(), true)
  await fits('.form-share-pop')
  assert.deepEqual(errors, [])
  console.log('PASS: add-field, long variable submenu, emoji and nested form-sharing menus fit small viewports and remain clickable.')
} finally { await browser.close() }
