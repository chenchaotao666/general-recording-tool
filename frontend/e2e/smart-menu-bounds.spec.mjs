import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)),
  server: { host: '127.0.0.1', port: 0 },
  plugins: [{
    name: 'menu-test-harness',
    resolveId(id) { if (id === 'virtual:menu-test') return '\0menu-test' },
    load(id) {
      if (id !== '\0menu-test') return
      return `
        import { createApp, h, withDirectives } from 'vue'
        import CellContextMenu from '/src/components/smart/grid/CellContextMenu.vue'
        import SmartMenu from '/src/components/smart/common/SmartMenu.vue'
        import bounds from '/src/smart/utils/menuBounds.js'
        document.body.innerHTML = '<div id="test"></div>'
        const style = document.createElement('style')
        style.textContent = ':root { --st-list-item-height:32px; --st-font-size:14px; --st-text-2:#222; } .field-test .fm-sub { display:none } .field-test .has-sub:hover > .fm-sub { display:block } .has-sub { position:relative }'
        document.head.append(style)
        let app
        window.mountMenu = mode => {
          app?.unmount()
          window.actions = []; window.closes = 0
          app = createApp({ render() {
            if (mode === 'cell') return h(CellContextMenu, { x:290, y:210, hasField:true, canCreate:true, canDelete:true, onAction:(...args) => window.actions.push(args), onClose:() => window.closes++ })
            const sub = h('div', { class:'fm-sub', style:'min-width:260px' }, Array.from({length:25}, (_,i) => h('button', { class:'mi', onClick:() => window.actions.push(i) }, 'Submenu item '+i)))
            return withDirectives(h(SmartMenu, { class:'field-test', style:'width:220px' }, () => [h('div', {class:'mi has-sub'}, ['Hover submenu', sub]), ...Array.from({length:30}, (_,i) => h('button',{class:'mi'}, 'Parent item '+i))]), [[bounds,{x:290,y:210}]])
          }})
          app.mount('#test')
        }
      `
    },
  }],
})
let browser
try {
  await server.listen()
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 320, height: 240 } })
  await page.route(`${origin}/menu-test`, route => route.fulfill({ contentType: 'text/html', body: '<html><body><script type="module">import "/@id/__x00__menu-test"</script></body></html>' }))
  await page.goto(`${origin}/menu-test`)
  await page.waitForFunction(() => window.mountMenu)
  await page.evaluate(() => window.mountMenu('field'))
  const parent = page.locator('.field-test')
  assert.ok(await parent.evaluate(el => el.scrollHeight > el.clientHeight))
  await parent.locator('.has-sub').hover()
  const sub = parent.locator('.fm-sub')
  await sub.waitFor({ state: 'visible' })
  const box = await sub.boundingBox()
  assert.ok(box.x >= 8 && box.y >= 8 && box.x + box.width <= 312 && box.y + box.height <= 232)
  assert.ok(await sub.evaluate(el => el.scrollHeight > el.clientHeight))
  await sub.locator('button').last().click()
  assert.deepEqual(await page.evaluate(() => window.actions), [24])
  await page.setViewportSize({ width: 180, height: 200 })
  await parent.evaluate(el => { el.scrollTop = 0 })
  await parent.locator('.has-sub').hover()
  const narrow = await sub.boundingBox()
  assert.ok(narrow.x >= 8 && narrow.x + narrow.width <= 172)
  await sub.locator('button').first().click()
  await page.setViewportSize({ width: 420, height: 240 })
  await page.evaluate(() => window.mountMenu('cell'))
  const cell = page.locator('.cell-context-menu')
  assert.ok(await cell.evaluate(el => el.scrollHeight > el.clientHeight))
  await cell.getByRole('menuitem', { name: '数据可视化' }).hover()
  const child = cell.locator('.cell-menu-sub')
  await child.waitFor({ state: 'visible' })
  await child.getByRole('menuitem', { name: '柱状图' }).click()
  assert.equal(await page.evaluate(() => window.actions[0][0]), 'viz-bar')
  assert.equal(await page.evaluate(() => window.closes), 1)
  await page.evaluate(() => window.mountMenu('cell'))
  await cell.getByRole('spinbutton', { name: '向下插入行数' }).fill('9')
  await page.keyboard.press('Enter')
  assert.deepEqual(await page.evaluate(() => window.actions[0]), ['insert-down', 9])
  await page.keyboard.press('Escape')
  assert.equal(await page.evaluate(() => window.closes), 2)
  console.log('PASS: scrollable parent/submenu, hover click outside parent bounds, narrow resize, insert quantity, Escape')
} finally {
  await browser?.close()
  await server.close()
}
