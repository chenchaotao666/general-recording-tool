import { chromium } from 'playwright'
import assert from 'node:assert/strict'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 480, height: 640 } })
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: [] }))
  await page.goto(process.env.BASE_URL || 'http://localhost:5173', { waitUntil: 'networkidle' })
  await page.evaluate(async () => {
    // Match Vite's versioned module URLs so provide/inject uses the same symbols as the components.
    const source = await (await fetch('/src/components/smart/automation/AutomationEditor.vue')).text()
    const { createApp, h, ref } = await import(source.match(/from "([^"]*\/vue\.js[^\"]*)"/)[1])
    const { default: ElementPlus, ElConfigProvider } = await import(source.match(/from "([^"]*\/element-plus\.js[^\"]*)"/)[1])
    const { default: AutomationEditor } = await import('/src/components/smart/automation/AutomationEditor.vue')
    const root = document.createElement('div')
    root.className = 'st-page'
    root.style.cssText = 'position:fixed;inset:0;background:white;z-index:1000;overflow:auto;padding:12px'
    document.body.append(root)
    const fields = [{ field_name: 'date', label: '日期测试', field_type: 'date', options: {} }, { field_name: 'choice', label: '选项测试', field_type: 'singleSelect', options: { options: [{ id: 'a', label: '选项 A', color: 'blue' }] } }]
    const rule = ref({ trigger: { type: 'recordUpdated', filter: { conditions: [] } }, actions: [{ id: 'create', type: 'createRecord', tableId: 1, mode: 'specified', values: [{ fieldId: 'date' }, { fieldId: 'choice' }] }, { id: 'message', type: 'sendMessage', content: [], buttons: [] }] })
    window.__automationRule = rule
    createApp({ setup: () => () => h(ElConfigProvider, { zIndex: 4000 }, { default: () => h(AutomationEditor, { modelValue: rule.value, 'onUpdate:modelValue': v => rule.value = v, tableId: 1, tableName: '测试表', tables: [{ id: 1, label: '测试表' }], fields, loadFields: async () => fields }) }) }).use(ElementPlus).mount(root)
  })
  async function fits(selector) {
    const el = page.locator(selector).last()
    await el.waitFor()
    await page.waitForTimeout(160)
    const r = await el.boundingBox(), v = page.viewportSize()
    assert.ok(r.x >= -1 && r.y >= -1 && r.x + r.width <= v.width + 1 && r.y + r.height <= v.height + 1, `${selector}: ${JSON.stringify(r)}`)
  }
  for (const viewport of [{ width: 480, height: 640 }, { width: 360, height: 280 }]) {
    await page.setViewportSize(viewport)
    await page.locator('.ae-create-trigger').first().click()
    await page.locator('.dvi-trigger').click()
    await fits('.dvi-pop:visible')
    await page.getByRole('button', { name: '具体日期', exact: true }).click()
    await fits('.el-picker__popper:visible')
    await page.locator('.el-date-table td.available:not(.prev-month):not(.next-month) .el-date-table-cell__text').filter({ hasText: /^15$/ }).click()
    assert.equal((await page.evaluate(() => window.__automationRule.value.actions[0].values[0].value)).type, 'static')
    await page.locator('.dvi-trigger').click()
    await page.locator('.dvi-pop .vm-item.has-sub').hover()
    await fits('.vm-sub-fields')
    await page.locator('.vm-sub-fields').getByText('日期测试', { exact: true }).click()
    assert.equal((await page.evaluate(() => window.__automationRule.value.actions[0].values[0].value)).type, 'var')
    assert.equal(await page.locator('.vm-sub').count(), 0)
    await page.locator('.vi-enum-trigger').click()
    await fits('.vi-option-pop:visible')
    await page.locator('.vi-option-row').click()
    assert.equal((await page.evaluate(() => window.__automationRule.value.actions[0].values[1].value)).value, 'a')
    await page.locator('.vi-enum-trigger').click()
    await page.locator('.vi-option-pop .vm-item.has-sub').filter({ hasText: '第1步' }).hover()
    await fits('.vm-sub-fields')
    await page.locator('.vm-sub-fields').getByText('选项测试', { exact: true }).click()
    assert.equal((await page.evaluate(() => window.__automationRule.value.actions[0].values[1].value)).type, 'var')
    await page.locator('.vi-var').click()
    await page.locator('.vi-vars-pop .vm-item.has-sub').filter({ hasText: '第1步' }).hover()
    await fits('.vm-sub-fields')
    await page.mouse.click(2, 2)
    assert.equal(await page.locator('.vm-sub').count(), 0)
    assert.equal(await page.locator('.ae-create-values').count(), 0)
    await page.locator('.me-add-button').click()
    await fits('.el-popover:visible')
    await page.getByPlaceholder('输入文本').fill('测试链接')
    await page.locator('.me-var-link').click()
    await page.locator('.vm-inline .vm-item.has-sub').filter({ hasText: '第1步' }).hover()
    await fits('.vm-sub-fields')
    await page.locator('.vm-sub-fields').getByText('记录链接', { exact: true }).click()
    assert.ok((await page.locator('.me-link-chip').textContent()).includes('记录链接'))
    await page.screenshot({ path: `${process.env.TEMP || '.'}/automation-popups-${viewport.width}.png` })
    await page.locator('.me-var-link').click()
    await page.locator('.vm-inline .vm-item.has-sub').filter({ hasText: '第1步' }).hover()
    await page.mouse.click(2, 2)
    assert.equal(await page.locator('.vm-sub').count(), 0)
    assert.equal(await page.locator('.me-button-form').count(), 0)
    await page.evaluate(() => { window.__automationRule.value.actions[0].values[1].value = undefined })
  }
  assert.deepEqual(errors, [])
  console.log('PASS Edge 480x640 and 360x280: nested date, option, variable and link selection; bounds and outside-close cleanup. All API requests intercepted; no writes or AI.')
} finally { await browser.close() }
