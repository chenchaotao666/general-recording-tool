// Run from frontend: node tests/gridScroll.browser.mjs
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
import { WIDE_COLUMN_BUFFER, NARROW_COLUMN_BUFFER } from '../src/smart/utils/adaptiveColumnBuffer.js'

const fixture = `import {createApp,h,ref} from 'vue';import EP from 'element-plus';import VXE from 'vxe-table';
import 'element-plus/dist/index.css';import 'vxe-table/lib/style.css';import '/src/smart/tokens.css';
import '/src/smart/scrollbars.css';
import Grid from '/src/components/smart/grid/SmartGrid.vue';
const rowHeight=ref('default');window.setHeight=v=>rowHeight.value=v;
const scenario=new URLSearchParams(location.search).get('scenario');
createApp({render:()=>h(Grid,{fields:Array.from({length:60},(_,i)=>({field_name:'f'+i,field_type:'text',label:'Field '+i})),
view:{config:{rowHeight:rowHeight.value,frozenFieldId:scenario==='frozen'||scenario==='group'?'f2':null}},
columnGroups:scenario==='group'?[{id:'group',name:'Group',field_names:['f1','f2','f3','f4']}]:[],
rows:Array.from({length:1000},(_,i)=>({id:i+1,__key:String(i+1),f0:'Row '+i})),height:780})}).use(EP).use(VXE).mount('#app')`
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
 const page = await browser.newPage({ viewport: { width: 1100, height: 900 } })
 const errors = []
 page.on('pageerror', e => errors.push(e.message))
 await page.goto(server.resolvedUrls.local[0] + '__scroll')
 await page.waitForFunction(() => window.__scrollTable?.reactData.tableData.length > 0)
 for (const mode of ['extraTall', 'default', 'tall', 'default', 'medium', 'default']) {
   await page.evaluate(mode => { window.setHeight(mode) }, mode)
   await page.waitForTimeout(400)
   if (mode !== 'default') await page.evaluate(() => window.__scrollTable.scrollTo(600, 1520))
   await page.waitForTimeout(300)
   const metrics = await page.evaluate(() => {
     const table = window.__scrollTable
     const body = document.querySelector('.vxe-table--main-wrapper .vxe-table--body-wrapper')
     const rect = body.getBoundingClientRect()
     const rows = [...body.querySelectorAll('tbody tr')].map(el => el.getBoundingClientRect()).filter(r => r.height > 0)
     return { height: table.reactData.rowHeight, bottom: Math.max(...rows.map(r => r.bottom)), viewportBottom: rect.bottom,
       top: Math.min(...rows.map(r => r.top)), viewportTop: rect.top, scrollLeft: table.getScroll().scrollLeft }
   })
   assert.ok(metrics.bottom >= metrics.viewportBottom - 2, JSON.stringify({mode, ...metrics}))
   assert.ok(metrics.top <= metrics.viewportTop + 2, JSON.stringify({mode, ...metrics}))
   assert.equal(metrics.scrollLeft, 600)
   if (mode === 'default') assert.equal(metrics.height, 36)
 }
 assert.deepEqual(errors, [])
 console.log('Row height changes: visible rows cover viewport, horizontal scroll preserved')
} finally { await browser.close(); await server.close() }
