import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const base = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1000, height: 600 } })
  const errors = []
  page.on('pageerror', e => { errors.push(e.message); console.error(e.message) })
  page.on('console', msg => { if (msg.type() === 'error') console.error(msg.text()) })
  await page.route('**/__nested-panel-test', route => route.fulfill({ contentType: 'text/html', body: String.raw`
    <!doctype html><html><head><meta charset="utf-8"></head><body><div id="app"></div><button id="outside" style="position:fixed;bottom:0;left:0">外部</button>
    <script type="module">
    import { createApp, h, ref } from '/node_modules/.vite/deps/vue.js'
    import ElementPlus from '/node_modules/.vite/deps/element-plus.js'
    import '/node_modules/element-plus/dist/index.css'
    import '/src/smart/tokens.css'
    import FillPanel from '/src/components/smart/panels/FillPanel.vue'
    import FilterPanel from '/src/components/smart/panels/FilterPanel.vue'
    import SortPanel from '/src/components/smart/panels/SortPanel.vue'
    import GroupPanel from '/src/components/smart/panels/GroupPanel.vue'
    import FieldFilterPop from '/src/components/smart/panels/FieldFilterPop.vue'
    const fields = [
      { field_name: 'status', label: '状态', field_type: 'multiSelect', options: { options: [{ id: 'a', label: 'Alpha' }, { id: 'b', label: 'Beta' }] } },
      { field_name: 'date', label: '日期', field_type: 'date' },
      ...Array.from({length: 30}, (_, i) => ({ field_name: 'f'+i, label: '字段'+i, field_type: 'text' })),
    ]
    createApp({ components: { FillPanel, FilterPanel, SortPanel, GroupPanel }, setup() {
      const active = ref(null)
      const rules = Array.from({length: 20}, (_, i) => ({ id: 'r'+i, fieldId: 'status', operator: 'hasAny', value: [] }))
      document.addEventListener('click', e => {
        if (!document.contains(e.target) || e.target.closest('.el-popper, .toolbar')) return
        active.value = null
      })
      return () => h('div', { class: 'toolbar' }, [
        [FillPanel, 'fill', { rules }], [FilterPanel, 'filter', {}],
        [SortPanel, 'sort', { sorts: [{ fieldId: 'status', direction: 'asc' }] }],
        [GroupPanel, 'group', { groups: [{ fieldId: 'status', direction: 'asc' }] }],
      ].map(([component, name, props]) => h(component, { ...props, fields, visible: active.value === name,
        'onUpdate:visible': v => active.value = v ? name : null }, { default: () => h('button', { id: name }, name) })))
    } }).use(ElementPlus).mount('#app')
    window.mountFieldFilter = () => {
      const host = document.createElement('div')
      host.id = 'field-filter-host'
      host.className = 'el-popper'
      host.style.cssText = 'position:fixed;left:20px;bottom:45px;width:320px;max-height:160px;overflow:auto;background:white'
      document.body.append(host)
      createApp({ setup() {
        const condition = ref({ fieldId: 'date', operator: 'eq', value: { mode: 'today' } })
        return () => h(FieldFilterPop, { field: fields[1], condition: condition.value, pinned: true,
          onChange: v => { window.fieldChange = v; condition.value = v }, onOpenPanel: () => window.openedPanel = true })
      } }).use(ElementPlus).mount(host)
    }
    </script></body></html>` }))
  await page.goto(`${base}/__nested-panel-test`)
  await page.locator('#fill').waitFor()
  const assertBounds = async locator => {
    const b = await locator.boundingBox(), v = page.viewportSize()
    assert.ok(b.x >= 0 && b.y >= 0 && b.x + b.width <= v.width + 1 && b.y + b.height <= v.height + 1, `out of viewport: ${JSON.stringify(b)} / ${JSON.stringify(v)}`)
  }
  for (const viewport of [{ width: 1000, height: 600 }, { width: 390, height: 420 }]) {
    await page.setViewportSize(viewport)
    await page.locator('#fill').click()
    const panel = page.locator('.el-popper:visible').filter({ has: page.locator('.flp') })
    await panel.waitFor(); await page.waitForTimeout(300)
    await assertBounds(panel)
    assert.ok(await page.locator('.flp-scroll').evaluate(el => el.scrollHeight > el.clientHeight), 'rules scroll internally')
    assert.ok(await page.locator('.flp').evaluate(el => el.scrollWidth <= el.clientWidth + 1), 'no horizontal overflow')
    await page.locator('.flp-row').first().locator('.enum-val').click()
    const enumPop = page.locator('.condition-value-pop:visible')
    await enumPop.waitFor()
    await enumPop.locator('input').fill('Beta')
    await enumPop.locator('.ev-item').click()
    assert.equal(await panel.isVisible(), true)
    await assertBounds(enumPop)
    await page.locator('.flp-head').click()
    const last = page.locator('.flp-row').last()
    await last.scrollIntoViewIfNeeded()
    await last.locator('.flp-color').click()
    const palette = page.locator('.fill-palette-pop:visible')
    await palette.waitFor(); await page.waitForTimeout(150)
    await assertBounds(palette)
    assert.equal(await palette.evaluate(el => !!el.closest('.flp-scroll')), false)
    await palette.locator('.flp-cell').first().click()
    await palette.locator('.el-checkbox').click()
    assert.equal(await panel.isVisible(), true)
    await page.locator('#outside').click()
    await panel.waitFor({ state: 'hidden' })
    assert.equal(await page.locator('.fill-palette-pop:visible').count(), 0)
  }
  await page.setViewportSize({ width: 1000, height: 600 })
  for (const name of ['sort', 'group']) {
    await page.locator('#' + name).click()
    await page.waitForTimeout(300)
    await page.locator('.tbfs:visible').click()
    const pick = page.locator('.st-pick-pop:visible')
    await pick.getByText('日期', { exact: true }).click()
    assert.equal(await page.locator('.tbfs:visible').count(), 1)
    assert.match(await page.locator('.tbfs:visible').textContent(), /日期/)
    await page.locator('#outside').click()
    assert.equal(await page.locator('.tbfs:visible').count(), 0)
  }
  await page.locator('#filter').click()
  await page.locator('.fp .tbp-add').click()
  await page.locator('.st-pick-pop:visible').getByText('日期', { exact: true }).click()
  await page.locator('.dv-mode .el-select__wrapper').click()
  await page.locator('.dv-mode-pop:visible').getByText('具体日期', { exact: true }).click()
  await page.locator('.dv-date input').click()
  const calendar = page.locator('.el-date-picker:visible')
  await calendar.waitFor()
  await calendar.locator('td.available:not(.prev-month):not(.next-month)').first().click()
  assert.equal(await page.locator('.fp:visible').count(), 1)
  assert.notEqual(await page.locator('.dv-date input').inputValue(), '')
  await page.locator('#outside').click()
  await page.locator('.fp').waitFor({ state: 'hidden' })
  await page.setViewportSize({ width: 390, height: 260 })
  await page.evaluate(() => window.mountFieldFilter())
  await page.locator('#field-filter-host .ffp-op').click()
  const operators = page.locator('.ffp-operator-pop:visible')
  await operators.waitFor(); await page.waitForTimeout(200)
  await assertBounds(operators)
  assert.equal(await operators.evaluate(el => !!el.closest('#field-filter-host')), false)
  assert.ok(await operators.locator('.ffp-menu').evaluate(el => el.scrollHeight > el.clientHeight), 'long operator list scrolls in low viewport')
  const lastOperator = operators.locator('.ffp-mi').last()
  const lastLabel = (await lastOperator.textContent()).trim()
  await lastOperator.click()
  assert.equal((await page.locator('#field-filter-host .ffp-op').textContent()).trim(), lastLabel)
  assert.ok(await page.evaluate(() => window.fieldChange?.operator))
  await page.locator('#field-filter-host [aria-label="更多"]').click()
  const more = page.locator('.ffp-more-pop:visible')
  await more.waitFor(); await page.waitForTimeout(150)
  await assertBounds(more)
  assert.equal(await more.evaluate(el => !!el.closest('#field-filter-host')), false)
  await more.getByText('打开筛选面板', { exact: true }).click()
  assert.equal(await page.evaluate(() => window.openedPanel), true)
  await more.waitFor({ state: 'hidden' })
  assert.deepEqual(errors, [])
  console.log('PASS: 1000×600 and 390×420 fill bounds, scrolling, body enum/palette interactions, sorting/grouping parent persistence, filter calendar selection and outside close.')
} finally { await browser.close() }
