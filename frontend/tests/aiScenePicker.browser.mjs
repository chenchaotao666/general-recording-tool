import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import {createApp,h,ref} from 'vue'
import EP from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import '/src/smart/controls.css'
import Picker from '/src/components/smart/ai/AiScenePicker.vue'
const categories=[{key:'recommend',label:'Recommended'},{key:'customer',label:'Customers'}]
const scenes=[{key:'custom',label:'Custom'}, {key:'summary',label:'Summary',category:'recommend',desc:'Summarize content'}, {key:'follow',label:'Follow up',category:'customer',desc:'Generate email for customers'}, {key:'code',label:'Code',category:'customer',local:true}, {key:'disabled',label:'Coming soon',category:'customer',disabled:true}]
createApp({setup(){const value=ref('custom');return()=>h('div',{style:'width:370px;margin:30px'},[h(Picker,{modelValue:value.value,categories,scenes,onChange:v=>{value.value=v;window.selected=v}})])}}).use(EP).mount('#app')
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
 await page.locator('.scene-trigger').click()
 const popup=page.locator('.ai-scene-picker-pop:visible')
 await popup.waitFor()
 await page.waitForFunction(()=>document.activeElement?.classList.contains('scene-search'))
 assert.equal(await popup.locator('.scene-categories .is-selected').textContent(),'Recommended')
 assert.equal(await popup.locator('.scene-search').evaluate(el=>getComputedStyle(el).paddingLeft),'12px')
 assert.equal(await popup.locator('.scene-list button').count(),1)
 await popup.getByRole('button',{name:'Customers',exact:true}).click()
 assert.equal(await popup.locator('.scene-list button').count(),2)
 assert.equal(await popup.locator('.scene-list button[aria-disabled="true"]').count(),0)
 assert.equal(Math.round((await popup.boundingBox()).width), Math.round((await page.locator('.scene-trigger').boundingBox()).width))
 const first = await popup.locator('.scene-list button').nth(0).boundingBox()
 const second = await popup.locator('.scene-list button').nth(1).boundingBox()
 assert.equal(first.height,32)
 assert.equal(first.y,second.y)
 assert.ok(second.x > first.x)
 assert.equal(await popup.locator('.scene-list button').first().locator('.scene-meta').textContent(),'LLM')
 await popup.locator('.scene-search').fill('email')
 assert.equal(await popup.locator('.scene-list button').count(),1)
 assert.ok(await popup.locator('.scene-custom').isVisible())
 await popup.locator('.scene-search').press('ArrowDown')
 await page.keyboard.press('Enter')
 await page.waitForFunction(()=>window.selected==='follow')
 await popup.waitFor({state:'hidden'})
 await page.locator('.scene-trigger').click()
 await popup.waitFor()
 await page.waitForFunction(()=>document.activeElement?.classList.contains('scene-search'))
 assert.equal(await popup.locator('.scene-search').inputValue(),'')
 assert.equal(await popup.locator('.scene-categories .is-selected').textContent(),'Customers')
 assert.ok((await popup.locator('.scene-list [aria-selected="true"]').textContent()).includes('Follow up'))
 await popup.locator('.scene-search').fill('no matches')
 assert.ok(await popup.locator('.scene-empty').isVisible())
 await popup.locator('.scene-custom').click()
 await page.waitForFunction(()=>window.selected==='custom')
 await page.setViewportSize({width:390,height:700})
 await page.locator('.scene-trigger').click()
 await popup.waitFor()
 await page.waitForFunction(()=>document.activeElement?.classList.contains('scene-search'))
 const box=await popup.boundingBox()
 assert.ok(box.x>=0 && box.x+box.width<=390)
 await popup.locator('.scene-search').press('Escape')
 await popup.waitFor({state:'hidden'})
 console.log('AI scene picker: categories, search, disabled items, keyboard, custom selection and narrow viewport passed')
} finally {await browser.close();await server.close()}
