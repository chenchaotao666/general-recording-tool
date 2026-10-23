import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium } from 'playwright'

// Mount the actual SFCs in a table without a backend or changes to application fixtures.
const html = `<!doctype html><html><head><style>
:root { --st-font-size: 14px; --st-primary: #4a54e2; }
body { margin: 0; font: 14px Arial; }
table { position: fixed; table-layout: fixed; border-collapse: collapse; }
td { padding: 0; height: 36px; }
</style></head><body><div id="fixture"></div><script type="module">
import { createApp, h, reactive, nextTick } from 'vue'
import SmartCellEditor from '/src/components/smart/grid/SmartCellEditor.vue'
import SelectCellPanel from '/src/components/smart/grid/SelectCellPanel.vue'
let app
window.mountEditor = async (kind, config = {}) => {
  app?.unmount()
  window.events = []
  const state = reactive({ left: 40, top: 40, width: 200, preview: true, text: 'short', ...config })
  window.state = state
  app = createApp({ render() {
    const field = kind === 'text'
      ? { field_name: 'value', field_type: 'text', options: {} }
      : { field_name: 'value', field_type: 'singleSelect', options: { options: Array.from({ length: 30 }, (_, i) => ({ id: String(i), label: i === 0 ? 'A very long option label '.repeat(12) : 'Option ' + i })) } }
    return h('table', { style: { left: state.left + 'px', top: state.top + 'px', width: state.width + 'px' } }, [
      h('tbody', [h('tr', [h('td', [h(kind === 'text' ? SmartCellEditor : SelectCellPanel, {
        field, record: { value: kind === 'text' ? state.text : null }, preview: state.preview,
        fillHandle: true, advanceOnEnter: true,
        onCommit: value => window.events.push(['commit', value]),
        onCancel: () => window.events.push(['cancel']),
        onEnterEdit: () => { state.preview = false },
        onFillStart: (event, td, rect) => window.events.push(['fill', td.tagName, { left: rect.left, top: rect.top, width: rect.width, height: rect.height }]),
      })])])]),
    ])
  } })
  app.mount('#fixture')
  await nextTick()
}
window.unmountEditor = () => app?.unmount()
</script></body></html>`
const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)), configFile: false,
  plugins: [vue(), { name: 'grid-overlay-fixture', configureServer(server) {
    server.middlewares.use('/__grid_overlay_test', async (req, res, next) => {
      try { res.setHeader('Content-Type', 'text/html'); res.end(await server.transformIndexHtml('/__grid_overlay_test', html)) }
      catch (error) { next(error) }
    })
  } }], server: { host: '127.0.0.1', port: 0 },
})
let browser
try {
  await server.listen()
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__grid_overlay_test`)
  await page.waitForFunction(() => !!window.mountEditor)
  const settle = () => page.evaluate(async () => {
    // Mount/resize uses RAF, followed by Vue rendering and a content measurement.
    for (let i = 0; i < 4; i++) await new Promise(requestAnimationFrame)
  })
  async function mount(kind, config) {
    await page.evaluate(({ kind, config }) => window.mountEditor(kind, config), { kind, config })
    await settle()
  }
  async function contained(selector) {
    const box = await page.locator(selector).boundingBox()
    const viewport = page.viewportSize()
    assert.ok(box && box.x >= 7.5 && box.y >= 7.5, `${selector} starts outside viewport: ${JSON.stringify(box)}`)
    assert.ok(box.x + box.width <= viewport.width - 7.5, `${selector} overflows right: ${JSON.stringify(box)}`)
    assert.ok(box.y + box.height <= viewport.height - 7.5, `${selector} overflows bottom: ${JSON.stringify(box)}`)
    return box
  }

  // Normal positioning remains cell-aligned; short content uses its actual height.
  await mount('text', { left: 40, top: 50, width: 200 })
  let box = await contained('.cell-overlay')
  assert.equal(box.x, 40); assert.equal(box.y, 50); assert.equal(box.width, 200)
  assert.equal(box.height, 36)
  await mount('text', { left: 760, top: 570, width: 180 })
  box = await contained('.cell-overlay')
  assert.equal(box.y, 600 - 8 - box.height)
  assert.ok(box.height < 50, 'short preview must not reserve the maximum text height')

  const longText = 'Long text 中文内容 '.repeat(180)
  await mount('text', { left: 760, top: 570, width: 220, text: longText })
  box = await contained('.cell-overlay')
  assert.equal(box.height, 220)
  assert.ok(await page.locator('.preview-text').evaluate(el => el.scrollHeight > el.clientHeight))
  // The fill event still carries the visible overlay rect and original td.
  await page.locator('.text-fill-handle').dispatchEvent('pointerdown', { button: 0 })
  const fill = await page.evaluate(() => window.events.find(e => e[0] === 'fill'))
  assert.equal(fill[1], 'TD')
  assert.deepEqual(fill[2], { left: box.x, top: box.y, width: box.width, height: box.height })
  await page.setViewportSize({ width: 240, height: 180 }); await settle()
  await contained('.cell-overlay')
  assert.ok(await page.locator('.preview-text').evaluate(el => el.scrollHeight > el.clientHeight))
  await page.setViewportSize({ width: 800, height: 600 }); await settle()
  await page.locator('.preview-text').dblclick()
  await page.locator('textarea').waitFor()
  await settle()
  await contained('.cell-overlay')
  assert.ok(await page.locator('textarea').evaluate(el => document.activeElement === el))
  await page.locator('textarea').evaluate(el => el.setSelectionRange(5, 12))
  await page.setViewportSize({ width: 180, height: 140 })
  await settle()
  await contained('.cell-overlay')
  const editing = await page.locator('textarea').evaluate(el => ({
    focused: document.activeElement === el, start: el.selectionStart, end: el.selectionEnd,
    value: el.value, max: parseFloat(getComputedStyle(el).maxHeight), height: el.getBoundingClientRect().height,
  }))
  assert.deepEqual([editing.focused, editing.start, editing.end, editing.value], [true, 5, 12, longText])
  assert.ok(editing.max <= 120 && editing.height <= 120)
  assert.deepEqual(await page.evaluate(() => window.events.filter(e => e[0] === 'commit')), [])
  await page.locator('textarea').fill('Saved after resize')
  await settle()
  await contained('.cell-overlay')
  await page.locator('textarea').press('Enter')
  assert.deepEqual(await page.evaluate(() => window.events.filter(e => e[0] === 'commit')), [['commit', 'Saved after resize']])

  // Initial edit at the negative left/top boundary, then shrinking and growing again.
  await mount('text', { left: -30, top: -10, width: 600, preview: false, text: longText })
  await contained('.cell-overlay')
  await page.setViewportSize({ width: 800, height: 600 }); await settle()
  box = await contained('.cell-overlay')
  assert.equal(box.width, 600)
  await page.locator('textarea').press('Escape')
  assert.deepEqual(await page.evaluate(() => window.events), [['cancel']])

  // Select panels must fit even when the anchor is wider than the viewport.
  await mount('select', { left: 740, top: 550, width: 900 })
  box = await contained('.sel-panel')
  assert.ok(box.y < 550, 'bottom row opens upward')
  await page.setViewportSize({ width: 180, height: 140 }); await settle()
  box = await contained('.sel-panel')
  assert.ok(await page.locator('.sel-panel').evaluate(el => parseFloat(el.style.minWidth) <= innerWidth - 16))
  assert.ok(await page.locator('.sel-list').evaluate(el => el.scrollHeight > el.clientHeight))
  assert.ok(await page.locator('.sel-search').evaluate(el => el === document.activeElement))
  await page.setViewportSize({ width: 800, height: 600 }); await settle()
  box = await contained('.sel-panel')
  assert.equal(box.width, 784, 'panel expands again after viewport growth')
  await page.locator('.sel-search').fill('Option 29'); await settle()
  box = await contained('.sel-panel')
  assert.ok(box.height < 150, 'filtered panel remeasures natural height')
  await page.locator('.sel-item').click()
  assert.deepEqual(await page.evaluate(() => window.events), [['commit', '29']])

  await mount('select', { left: -40, top: 10, width: 120 })
  box = await contained('.sel-panel')
  assert.ok(box.y > 40, 'top row opens downward')
  await page.setViewportSize({ width: 180, height: 90 }); await settle()
  await page.evaluate(() => { window.state.top = 22 })
  await page.evaluate(() => window.dispatchEvent(new Event('resize'))); await settle()
  await contained('.sel-panel')
  assert.ok(await page.locator('.sel-panel').evaluate(el => el.scrollHeight > el.clientHeight), 'very short viewport scrolls the panel chrome internally')
  assert.ok(await page.locator('.sel-list').evaluate(el => el.clientHeight > 0), 'short viewport keeps a scrollable option row accessible')
  await page.locator('.sel-panel').evaluate(el => { el.scrollTop = el.scrollHeight })
  await page.locator('.sel-list').evaluate(el => { el.scrollTop = el.scrollHeight })
  await page.locator('.sel-item').last().click()
  assert.deepEqual(await page.evaluate(() => window.events), [['commit', '29']])
  await page.evaluate(() => window.unmountEditor())
  await page.setViewportSize({ width: 800, height: 600 }); await settle()
  assert.equal(await page.locator('.sel-panel, .cell-overlay').count(), 0)
  assert.deepEqual(errors, [])
  console.log('PASS: text preview/edit bounds, fill anchor, resize focus/selection, save/cancel; select width, height, flipping, filtering, internal scroll and cleanup (real Edge layout).')
} finally {
  await browser?.close()
  await server.close()
}
