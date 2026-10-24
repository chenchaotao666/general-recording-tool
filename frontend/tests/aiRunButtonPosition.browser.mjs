import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import {createApp,h,ref} from 'vue'
import EP from 'element-plus'
import 'element-plus/dist/index.css'
import Run from '/src/components/smart/ai/AiRunButton.vue'
createApp({setup(){const props=ref({x:706,y:210,anchorRect:{left:500,top:200,bottom:250}});window.move=v=>props.value=v;return()=>h(Run,props.value)}}).use(EP).mount('#app')
`
const server=await createServer({server:{host:'127.0.0.1',port:0},plugins:[{
name:'ai-run-position',resolveId(id){if(id==='/__run.js')return id},load(id){if(id==='/__run.js')return code},
configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__run')return next();res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__run.js"></script>')})}
}]})
await server.listen()
const browser=await chromium.launch()
try {
 const page=await browser.newPage({viewport:{width:1000,height:700}})
 await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__run`)
 await page.locator('.arb').waitFor()
 const settle=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))
 await settle()
 let box=await page.locator('.arb').boundingBox()
 assert.equal(box.x,706)
 assert.equal(box.y,208,'moves up 2px in total')
 await page.evaluate(()=>window.move({x:986,y:210,anchorRect:{left:780,top:200,bottom:250}}))
 await settle()
 box=await page.locator('.arb').boundingBox()
 assert.equal(box.x+box.width,774,'right overflow flips to outside left edge of cell')
 assert.equal(box.y,208)
 await page.locator('.arb-dd').click()
 await page.locator('.arb-menu').waitFor()
 await settle()
 const menu=await page.locator('.arb-menu').boundingBox()
 assert.ok(menu.x>=12 && menu.x+menu.width<=988)
 await page.evaluate(()=>window.move({x:986,y:210,anchorRect:{left:20,top:200,bottom:250}}))
 await settle()
 box=await page.locator('.arb').boundingBox()
 assert.ok(box.y+box.height<200,'wide cell fallback stays above content')
 console.log('PASS: right placement, left flip, 2px offset, menu bounds and wide-cell fallback')
} finally {await browser.close();await server.close()}
