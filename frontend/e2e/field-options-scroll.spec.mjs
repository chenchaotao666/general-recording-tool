import assert from 'node:assert/strict'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createServer } from 'vite'
import { chromium } from 'playwright'

const html = `<!doctype html><html><body><div id="app" class="st-page"></div><script type="module">
import { createApp, h, ref, nextTick } from 'vue'
import EP, { ElConfigProvider } from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import FieldConfig from '/src/components/smart/panels/FieldConfigDialog.vue'
const type = ref('singleSelect'), visible = ref(false)
window.setType = async value => { visible.value = false; type.value = value; await nextTick(); visible.value = true }
createApp({ render: () => h(ElConfigProvider, { zIndex: 4000 }, { default: () => h(FieldConfig, {
  key: type.value, visible: visible.value, at: { x: 70, y: 70 },
  field: { field_name: 'status', label: '产品名称', field_type: type.value, options: { options: Array.from({ length: 40 }, (_, i) => ({ id: 'o' + i, label: '选项 ' + i, color: 'blue' })) } }, fields: [],
}) }) }).use(EP).mount('#app')
</script></body></html>`
const server = await createServer({ server: { host: '127.0.0.1', port: 0 }, plugins: [{ name: 'field-options-fixture', configureServer(s) {
  s.middlewares.use('/__field_options', async (req, res, next) => {
    try { res.setHeader('Content-Type', 'text/html'); res.end(await s.transformIndexHtml('/__field_options', html)) } catch (error) { next(error) }
  })
} }] })
let browser
try {
  await server.listen()
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route(/\/api\/(?!index\.js)/, route => route.fulfill({ json: { items: [], tables: [], functions: [], categories: [] } }))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__field_options`)
  await page.waitForFunction(() => typeof window.setType === 'function')
  for (const type of ['singleSelect', 'multiSelect']) {
    await page.evaluate(type => window.setType(type), type)
    for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 420 }]) {
      await page.setViewportSize(viewport)
      await page.locator('.fcd-optbox').waitFor()
      await page.waitForTimeout(350)
      const before = await page.locator('.st-fcd-options').evaluate(el => {
        const list = el.querySelector('.fcd-optbox'), footer = el.querySelector('.fcd-foot'), name = el.querySelector('.fcd-name')
        return { scroll: el.scrollHeight, client: el.clientHeight, listScroll: list.scrollHeight, listClient: list.clientHeight, footerY: footer.getBoundingClientRect().y, nameY: name.getBoundingClientRect().y, bounds: el.getBoundingClientRect().toJSON() }
      })
      assert(before.scroll <= before.client + 1, JSON.stringify(before))
      assert(before.listScroll > before.listClient && before.listClient > 32)
      assert(before.bounds.y >= 0 && before.bounds.bottom <= viewport.height)
      await page.locator('.fcd-optbox').evaluate(el => { el.scrollTop = el.scrollHeight })
      const after = await page.locator('.st-fcd-options').evaluate(el => ({ top: el.scrollTop, footerY: el.querySelector('.fcd-foot').getBoundingClientRect().y, nameY: el.querySelector('.fcd-name').getBoundingClientRect().y }))
      assert.equal(after.top, 0)
      assert.equal(after.footerY, before.footerY)
      assert.equal(after.nameY, before.nameY)
      await page.locator('.fcd-opt-row input').last().fill('最后一项已修改')
      await page.locator('.fcd-opt-row input').last().press('Tab')
      await page.waitForTimeout(100)
      const count = await page.locator('.fcd-opt-row').count()
      await page.locator('.fcd-add').click()
      await page.waitForTimeout(150)
      console.log(type, viewport, 'rows', count, await page.locator('.fcd-opt-row').count())
      await page.screenshot({ path: join(tmpdir(), 'field-options-scroll.png') })
      assert.equal(await page.locator('.fcd-opt-row').count(), count + 1)
      const footer = await page.locator('.fcd-foot').boundingBox()
      assert(footer.y + footer.height <= viewport.height)
    }
  }
  await page.screenshot({ path: join(tmpdir(), 'field-options-scroll.png') })
  assert.deepEqual(errors, [])
  console.log('PASS: single/multi field option lists scroll independently; header/footer stay visible through resize, editing and adding options.')
} finally { await browser?.close(); await server.close() }
