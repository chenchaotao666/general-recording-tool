import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import {createApp,h} from 'vue'
import EP from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import Editor from '/src/components/smart/ai/AiFieldEditor.vue'
createApp({render:()=>h(Editor,{tableId:7,x:720,y:40,field:{label:'二维码',options:{scene:'qrcode',outputType:'file'}},fields:[],rows:[]})}).use(EP).mount('#app')
`
const server=await createServer({server:{host:'127.0.0.1',port:0},plugins:[{
name:'composer-two-lines',resolveId(id){if(id==='/__two.js')return id},load(id){if(id==='/__two.js')return code},
configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__two')return next();res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__two.js"></script>')})}
}]})
await server.listen()
const browser=await chromium.launch()
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 await page.route('**/api/smart/ai/scenes',r=>r.fulfill({json:{categories:[],scenes:[{key:'qrcode',label:'二维码',local:true,outputType:'file'}]}}))
 await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__two`)
 const editor=page.locator('.aic-editor')
 await editor.waitFor()
 const size=await editor.evaluate(el=>{
   el.innerHTML='<div><span class="aic-chip st-field-rich-chip" contenteditable="false">客户名称 ×</span></div><div><span class="aic-chip st-field-rich-chip" contenteditable="false">客户等级客户等级客户等级 ×</span></div>'
   return {height:el.clientHeight,scroll:el.scrollHeight}
 })
 assert.equal(size.scroll,size.height,'two chip rows must fit without vertical overflow')
 console.log('PASS: two field-chip lines fit without scrolling',size)
} finally {await browser.close();await server.close()}
