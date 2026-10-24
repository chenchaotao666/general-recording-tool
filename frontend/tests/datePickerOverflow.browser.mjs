import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import {createApp,h,ref} from 'vue'
import EP,{ElDatePicker} from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
createApp({setup(){const value=ref('2026-10-17');return()=>h('div',{class:'st-page',style:'position:fixed;bottom:30px;left:100px'},[h(ElDatePicker,{modelValue:value.value,valueFormat:'YYYY-MM-DD'})])}}).use(EP).mount('#app')
`
const server=await createServer({server:{host:'127.0.0.1',port:0},plugins:[{
name:'scene-picker-review',resolveId(id){if(id==='/__picker.js')return id},load(id){if(id==='/__picker.js')return code},
configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__picker')return next();res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__picker.js"></script>')})}
}]})
await server.listen()
const browser=await chromium.launch()
try {
 const page=await browser.newPage({viewport:{width:1000,height:800}})
 await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__picker`)
 await page.locator('input').click()
 const popup=page.locator('.el-picker__popper:visible')
 await popup.waitFor()
 await page.waitForTimeout(350)
 assert.ok((await popup.getAttribute('data-popper-placement')).startsWith('top'))
 assert.equal(await popup.evaluate(e=>getComputedStyle(e).overflowY),'visible')
 const panel=popup.locator('.el-picker-panel')
 assert.ok(await panel.evaluate(e=>e.scrollHeight<=e.clientHeight+1))
 await page.setViewportSize({width:1000,height:300})
 await page.waitForTimeout(200)
 assert.ok(await panel.evaluate(e=>e.scrollHeight>e.clientHeight))
 assert.ok((await popup.boundingBox()).height<=276)
 console.log('Calendar above input has no scrollbar; small viewport retains content scrolling')
} finally {await browser.close();await server.close()}
