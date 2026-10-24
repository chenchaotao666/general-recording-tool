// Run from frontend: node tests/gridScroll.browser.mjs
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
import { WIDE_COLUMN_BUFFER, NARROW_COLUMN_BUFFER } from '../src/smart/utils/adaptiveColumnBuffer.js'

const fixture = `import {createApp,h} from 'vue';import EP from 'element-plus';import VXE from 'vxe-table';
import 'element-plus/dist/index.css';import 'vxe-table/lib/style.css';import '/src/smart/tokens.css';
import '/src/smart/scrollbars.css';
import Grid from '/src/components/smart/grid/SmartGrid.vue';
const scenario=new URLSearchParams(location.search).get('scenario');
createApp({render:()=>h(Grid,{fields:Array.from({length:60},(_,i)=>({field_name:'f'+i,field_type:'text',label:'Field '+i})),
view:{config:{frozenFieldId:scenario==='frozen'||scenario==='group'?'f2':null}},
columnGroups:scenario==='group'?[{id:'group',name:'Group',field_names:['f1','f2','f3','f4']}]:[],
rows:Array.from({length:1000},(_,i)=>({id:i+1,__key:String(i+1),f0:'Row '+i})),height:480})}).use(EP).use(VXE).mount('#app')`
const server = await createServer({ server: { port: 5185 }, plugins: [{
  name: 'scroll-fixture', enforce: 'pre',
  transform(source, id) {
    if (id.replaceAll('\\', '/').endsWith('/smart/grid/SmartGrid.vue')) {
      return source.replace('</script>', 'onMounted(() => { window.__scrollTable = gridRef.value })\n</script>')
    }
  },
  resolveId(id) { if (id === '/__scroll.js') return id },
  load(id) { if (id === '/__scroll.js') return fixture },
  configureServer(s) { s.middlewares.use((req, res, next) => {
    if (req.url.split('?')[0] !== '/__scroll') return next()
    res.setHeader('Content-Type', 'text/html')
    res.end('<div id="app"></div><script type="module" src="/__scroll.js"></script>')
  }) },
}] })
await server.listen()
const browser = await chromium.launch()
try {
 for (const scenario of ['plain', 'frozen', 'group']) {
  const page = await browser.newPage({ viewport: { width: 900, height: 600 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(server.resolvedUrls.local[0] + '__scroll?scenario=' + scenario)
  await page.waitForFunction(size => window.__scrollTable?.internalData.scrollXStore.preloadSize === size, WIDE_COLUMN_BUFFER)
  for (const axis of ['horizontal', 'vertical']) {
    const thumb = page.locator('.st-' + axis + '-thumb')
    await thumb.waitFor({ state: 'visible' })
    const box = await thumb.boundingBox()
    const x = box.x + box.width / 2, y = box.y + box.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x + (axis === 'horizontal' ? 80 : -100), y + (axis === 'vertical' ? 100 : -80), { steps: 12 })
    await page.mouse.up()
    const handle = axis === 'horizontal' ? '.vxe-table--scroll-x-handle' : '.vxe-table--scroll-y-handle'
    await page.waitForFunction(({ handle, axis }) => document.querySelector(handle)[axis === 'horizontal' ? 'scrollLeft' : 'scrollTop'] > 0, { handle, axis })
    assert.equal(await page.locator('.st-' + axis + '-track.dragging').count(), 0)
    console.log(axis + ' off-track drag passed')
  }
  await page.evaluate(() => window.__scrollTable.scrollTo(3200, 3600))
  await page.waitForTimeout(350)
  const box = await page.locator('.st-vertical-thumb').boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  let reduced = false
  for (let step = 1; step <= 20; step++) {
    await page.mouse.move(box.x - 100, box.y + box.height / 2 + step * 3)
    await page.waitForTimeout(30)
    reduced ||= await page.evaluate(size => window.__scrollTable.internalData.scrollXStore.preloadSize === size, NARROW_COLUMN_BUFFER)
  }
  assert.ok(reduced, scenario + ': sustained vertical drag should narrow buffer')
  await page.mouse.up()
  await page.waitForFunction(size => window.__scrollTable.internalData.scrollXStore.preloadSize === size, WIDE_COLUMN_BUFFER)
  assert.equal(await page.evaluate(() => window.__scrollTable.getScroll().scrollLeft), 3200)
  console.log(scenario + ': adaptive buffer and horizontal position passed')
  await page.waitForTimeout(250)
  assert.deepEqual(errors, [])
  await page.close()
 }
} finally {
  await browser.close()
  await server.close()
}
