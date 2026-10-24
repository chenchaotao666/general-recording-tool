import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import {createApp,h} from 'vue'
import EP from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import Editor from '/src/components/smart/ai/AiFieldEditor.vue'
createApp({render:()=>h(Editor,{tableId:7,x:720,y:40,field:{label:'BMI',options:{scene:'cvBmi',outputType:'number'}},fields:[],rows:[],onEditFormula:payload=>window.formulaEdit=payload})}).use(EP).mount('#app')
`
const server=await createServer({server:{host:'127.0.0.1',port:0},plugins:[{
name:'template-help',resolveId(id){if(id==='/__help.js')return id},load(id){if(id==='/__help.js')return code},
configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__help')return next();res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__help.js"></script>')})}
}]})
await server.listen()
const browser=await chromium.launch()
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 await page.route('**/api/smart/ai/scenes',r=>r.fulfill({json:{categories:[],scenes:[{key:'cvBmi',label:'BMI',local:true,formula:'1+2',formulaDisplay:'1+2',outputType:'number',inputRoles:[]}]}}))
 await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__help`)
 const trigger=page.locator('.ati-help-trigger'), panel=page.locator('.ai-selected-template-pop')
 await trigger.waitFor()
 const before=await page.locator('.afe').boundingBox()
 for(let i=0;i<3;i++) {
   await trigger.hover()
   await panel.waitFor({state:'visible'})
   // Catch delayed Popover updates that used to close the panel after a click.
   await page.waitForTimeout(400)
   assert.ok(await panel.isVisible())
   const box=await panel.boundingBox(), anchor=await trigger.boundingBox()
   assert.ok(box.x>=anchor.x+anchor.width || box.x+box.width<=anchor.x)
   assert.equal((await page.locator('.afe').boundingBox()).height,before.height)
   await panel.locator('.ati-prompt summary').click()
   assert.ok(await panel.isVisible(),'clicking details must not dismiss the panel')
   if(i===0) await page.locator('.afe-name').hover()
   else if(i===1) await page.keyboard.press('Escape')
   else await page.locator('.afe-name').click()
   await panel.waitFor({state:'hidden'})
 }
 await trigger.hover()
 await page.getByRole('button',{name:'编辑公式',exact:true}).click()
 await page.getByText('编辑公式内容需要将 AI 字段转为公式字段',{exact:true}).waitFor()
 await page.locator('.el-message-box').getByRole('button',{name:'取消',exact:true}).click()
 assert.equal(await page.evaluate(()=>window.formulaEdit),undefined)
 await trigger.hover()
 await page.getByRole('button',{name:'编辑公式',exact:true}).click()
 await page.locator('.el-message-box').getByRole('button',{name:'继续编辑',exact:true}).click()
 await page.waitForFunction(()=>!!window.formulaEdit)
 assert.deepEqual(await page.evaluate(()=>window.formulaEdit),{label:'BMI',field_type:'formula',config:{formula:'1+2',returnType:'number'}})
 await page.context().grantPermissions(['clipboard-read','clipboard-write'])
 await trigger.hover()
 await page.getByRole('button',{name:'复制公式',exact:true}).click()
 assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'1+2')
 console.log('PASS: hover details, edit cancellation/confirmation payload, clipboard copy')
} finally {await browser.close();await server.close()}
