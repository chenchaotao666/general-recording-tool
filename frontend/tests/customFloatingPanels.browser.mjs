// Run: node tests/customFloatingPanels.browser.mjs
// Real Chromium layout checks; all API responses are fixtures, no saved data is changed.
import assert from 'node:assert/strict'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createServer } from 'vite'
import { chromium } from 'playwright'

const code = `
import { createApp, h, ref } from 'vue'
import EP, { ElConfigProvider, useZIndex } from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import Market from '/src/components/smart/ai/AiFieldPanel.vue'
import Editor from '/src/components/smart/ai/AiFieldEditor.vue'
import Run from '/src/components/smart/ai/AiRunButton.vue'
import Formula from '/src/components/smart/formula/FormulaEditor.vue'
const fields = [{ field_name: 'text', label: '名称', field_type: 'text' }]
const child = { setup() {
  const kind = ref('market'), visible = ref(false), xy = ref({ x: 2000, y: 1000 }), key = ref(0)
  const { nextZIndex } = useZIndex()
  window.show = (value) => { kind.value = value; key.value++; visible.value = false }
  window.toggleFormula = (value) => visible.value = value
  window.move = (x, y) => xy.value = { x, y }
  window.nextLayer = nextZIndex
  return () => h(({ market: Market, editor: Editor, run: Run, formula: Formula })[kind.value], {
    key: key.value, ...xy.value, visible: visible.value, tableId: 1, fields,
    field: { field_name: 'ai', label: 'AI字段', field_type: 'ai', options: { inputFields: ['text'], systemPrompt: '较长的指令内容。'.repeat(100) } },
  })
}}
createApp({ render: () => h(ElConfigProvider, { zIndex: 9000 }, { default: () => h(child) }) }).use(EP).mount('#app')
`
const server = await createServer({ server: { host: '127.0.0.1', port: 0 }, plugins: [{
  name: 'custom-panel-test',
  resolveId(id) { if (id === '/__panel-test.js') return id },
  load(id) { if (id === '/__panel-test.js') return code },
  configureServer(s) { s.middlewares.use((req, res, next) => {
    if (req.url !== '/__panel-test') return next()
    res.setHeader('Content-Type', 'text/html')
    res.end('<meta name="viewport" content="width=device-width, initial-scale=1"><div id="app" class="st-page"></div><script type="module" src="/__panel-test.js"></script>')
  }) },
}] })
await server.listen()
const browser = await chromium.launch()
try {
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', error => { errors.push(error.message); console.error(error.message) })
  page.on('console', message => { if (message.type() === 'error') console.error(message.text()) })
  await page.route(/\/api\/smart\//, route => {
    const url = route.request().url()
    let data = {}
    if (url.endsWith('/ai/scenes')) data = { categories: [{ key: 'recommend', label: '推荐' }], scenes: [
      { key: 'classify', label: '分类', category: 'recommend', desc: '分类场景', prompt: '按内容分类', outputType: 'text' },
      { key: 'custom', label: '自定义 AI 字段', outputType: 'text' },
    ] }
    if (url.endsWith('/ai/quota')) data = { used: 1, limit: 100 }
    if (url.endsWith('/ai/configure')) data = { config: { title: '分类结果', outputType: 'text', inputFields: ['text'], systemPrompt: '分类' }, preview: [] }
    if (url.endsWith('/formula/functions')) data = { categories: ['文本'], functions: Array.from({ length: 8 }, (_, i) => ({ name: 'CONCAT' + i, category: '文本', signature: 'CONCAT(文本1, 文本2)', desc: '拼接文本', examples: [{ code: 'CONCAT("a", "b")', result: 'ab' }] })), operators: [] }
    if (url.endsWith('/formula/preview')) data = { ok: true, blank: true, row_values: {} }
    return route.fulfill({ json: data })
  })
  await page.goto(server.resolvedUrls.local[0] + '__panel-test')
  await page.waitForSelector('.aip')
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  async function bounded(selector) {
    await settle()
    const b = await page.locator(selector).boundingBox()
    const v = page.viewportSize()
    assert(b && b.width > 0 && b.height > 0, selector + ' is rendered')
    assert(b.x >= 11 && b.y >= 11 && b.x + b.width <= v.width - 11 && b.y + b.height <= v.height - 11, selector + ' within viewport: ' + JSON.stringify({ b, v }))
    return b
  }
  for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 600 }, { width: 375, height: 667 }, { width: 320, height: 240 }]) {
    await page.setViewportSize(viewport)
    await page.evaluate(() => window.show('market'))
    await page.waitForSelector('.aip-scene')
    await bounded('.aip')
    assert(await page.locator('.aip-mask').evaluate(el => Number(el.style.zIndex)) > 9000)
    if (viewport.width <= 1056) {
      assert.equal(await page.locator('.aip').evaluate(el => getComputedStyle(el).flexDirection), 'column')
      await page.locator('.aip-custom').scrollIntoViewIfNeeded()
      await page.locator('.aip-custom').click()
      await bounded('.aip')
    }
    await page.evaluate(() => window.show('editor'))
    await page.waitForSelector('.afe-name')
    await bounded('.afe')
    await page.locator('.afe-sel').last().click()
    const options = page.locator('.el-select__popper:visible')
    await options.waitFor()
    await settle()
    const optionBounds = await options.boundingBox()
    assert(optionBounds.x >= 0 && optionBounds.y >= 0 && optionBounds.x + optionBounds.width <= viewport.width + 1 && optionBounds.y + optionBounds.height <= viewport.height + 1)
    const textOption = options.locator('.el-select-dropdown__item').first()
    await textOption.click()
    await page.locator('.afe-foot .primary').scrollIntoViewIfNeeded()
    await bounded('.afe-foot .primary')
    await page.evaluate(() => window.show('formula'))
    await page.evaluate(() => window.toggleFormula(true))
    await page.waitForSelector('.fxe')
    await bounded('.fxe')
    const z = await page.locator('.fxe-mask').evaluate(el => Number(el.style.zIndex))
    assert(z > 9000)
    await page.locator('.fxe-panes').evaluate(el => el.scrollLeft = el.scrollWidth)
    await page.locator('.fxe-doc').scrollIntoViewIfNeeded()
    assert(await page.locator('.fxe-doc').evaluate(el => el.getBoundingClientRect().right <= innerWidth - 11))
    await page.locator('.fxe-editor').fill('C')
    await page.locator('.fxe-editor').press('End')
    await page.waitForSelector('.fxe-ac')
    await bounded('.fxe-ac')
    assert(await page.locator('.fxe-ac').evaluate(el => Number(el.style.zIndex)) > z)
    await page.locator('.fxe-editor').press('ArrowDown')
    await page.locator('.fxe-editor').press('Tab')
    assert.match(await page.locator('.fxe-editor').innerText(), /CONCAT\d\(\)/)
    await page.evaluate(() => window.toggleFormula(false))
    await page.evaluate(() => window.toggleFormula(true))
    await page.waitForSelector('.fxe')
    await bounded('.fxe')
    assert(await page.locator('.fxe-mask').evaluate(el => Number(el.style.zIndex)) > z)
    await page.evaluate(() => window.show('run'))
    await page.waitForSelector('.arb')
    await page.evaluate(() => window.move(innerWidth - 20, innerHeight - 20))
    const button = await bounded('.arb')
    await page.locator('.arb-dd').click()
    const menu = await bounded('.arb-menu')
    assert(menu.y + menu.height < button.y, 'bottom menu flips upward')
    assert(menu.x < button.x, 'right menu aligns leftward')
    await page.evaluate(() => window.move(12, 12))
    const movedButton = await bounded('.arb')
    const movedMenu = await bounded('.arb-menu')
    assert(movedMenu.y > movedButton.y + movedButton.height, 'top menu opens downward')
    console.log('PASS viewport', viewport.width, viewport.height)
  }
  // The usage confirmation stays above its dynamic parent and remains reachable.
  await page.setViewportSize({ width: 375, height: 500 })
  await page.evaluate(() => window.show('market'))
  await page.waitForSelector('.aip-custom')
  await page.locator('.aip-custom').click()
  await page.locator('.aic-editor').fill('提取名称')
  await page.locator('.aic-send').click()
  await page.locator('.aip-res-ops .primary').click()
  await bounded('.aip-use')
  assert(await page.locator('.aip-use').evaluate(el => {
    const r = el.getBoundingClientRect()
    return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2))
  }), 'confirmation is above parent')
  await page.locator('.aip-use').screenshot({ path: join(tmpdir(), 'custom-ai-confirm.png') })
  await page.setViewportSize({ width: 320, height: 240 })
  await bounded('.aip-use')
  await page.locator('.aip-use .block').last().scrollIntoViewIfNeeded()
  await bounded('.aip-use .block:last-child')
  await page.evaluate(() => window.show('formula'))
  await page.evaluate(() => window.toggleFormula(true))
  await page.waitForSelector('.fxe')
  await bounded('.fxe')
  await page.screenshot({ path: join(tmpdir(), 'custom-formula-short.png') })
  await page.evaluate(() => window.show('run'))
  await page.waitForSelector('.arb')
  await page.locator('.arb-dd').click()
  // Resize already-open menus and panels, rather than only mounting in a small viewport.
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(() => window.move(1400, 860))
  await settle()
  await page.setViewportSize({ width: 320, height: 240 })
  await bounded('.arb'); await bounded('.arb-menu')
  for (const [kind, selector] of [['market', '.aip'], ['editor', '.afe'], ['formula', '.fxe']]) {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.evaluate(value => window.show(value), kind)
    if (kind === 'formula') await page.evaluate(() => window.toggleFormula(true))
    await page.waitForSelector(selector)
    await bounded(selector)
    await page.setViewportSize({ width: 320, height: 240 })
    await bounded(selector)
  }
  assert.deepEqual(errors, [])
  console.log('PASS nested confirmation, live resize and no browser runtime errors')
} finally {
  await browser.close()
  await server.close()
}
