import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import {createApp,h,ref,nextTick} from 'vue'
import EP from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import Panel from '/src/components/smart/panels/TableSettingsPanel.vue'
const fields=Array.from({length:205},(_,i)=>({field_name:'f'+i,label:'Field '+i,field_type:'text'}))
createApp({setup(){const visible=ref(false);window.measure=async(value)=>{const start=performance.now();visible.value=value;await nextTick();await new Promise(requestAnimationFrame);return performance.now()-start};return()=>h(Panel,{visible:visible.value,'onUpdate:visible':v=>visible.value=v,fields,view:{config:{}},onFieldAction:(cmd,f)=>window.action=[cmd,f.field_name]},()=>h('button',{id:'trigger'},'Settings'))}}).use(EP).mount('#app')
`
const server=await createServer({server:{host:'127.0.0.1',port:0},plugins:[{
name:'settings-performance',resolveId(id){if(id==='/__settings.js')return id},load(id){if(id==='/__settings.js')return code},
configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__settings')return next();res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__settings.js"></script>')})}
}]})
await server.listen()
const browser=await chromium.launch()
try {
 const page=await browser.newPage({viewport:{width:1200,height:800}})
 await page.goto('http://127.0.0.1:'+server.httpServer.address().port+'/__settings')
 await page.waitForFunction(()=>!!window.measure)
 const timings=[]
 for(let i=0;i<3;i++){
   timings.push({open:await page.evaluate(()=>window.measure(true)),close:await page.evaluate(()=>window.measure(false))})
 }
 console.log(JSON.stringify({fields:205,timings}))
 if(process.env.BASELINE)process.exitCode=0
 else {
   assert.ok(timings.every(t=>t.open<500 && t.close<500),'Panel should not block a frame for half a second')
   await page.evaluate(()=>window.measure(true))
   const popup=page.locator('.st-ts-pop:visible')
   assert.equal(await popup.locator('.field-row').count(),205)
   await popup.locator('.field-row').last().locator('.f-more').click()
   await page.locator('.ts-field-menu:visible').getByRole('button',{name:'修改字段'}).click()
   assert.deepEqual(await page.evaluate(()=>window.action),['edit','f204'])
   await page.locator('.ts-field-menu').waitFor({state:'hidden'})
   await page.evaluate(()=>window.measure(true))
   const more=popup.locator('.field-row').last().locator('.f-more')
   await more.click()
   await page.locator('.ts-field-menu:visible').waitFor()
   await more.click()
   await page.locator('.ts-field-menu').waitFor({state:'hidden'})
   await more.focus()
   await page.keyboard.press('Enter')
   await page.locator('.ts-field-menu:visible').getByRole('button',{name:'创建副本'}).click()
   assert.deepEqual(await page.evaluate(()=>window.action),['duplicate','f204'])
   await page.evaluate(()=>window.measure(false))
   await page.locator('.ts-field-menu').waitFor({state:'hidden'})
 }
} finally {await browser.close();await server.close()}
