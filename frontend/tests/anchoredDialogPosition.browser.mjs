// Run: node tests/anchoredDialogPosition.browser.mjs
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const code = `
import { createApp, h, ref, withDirectives } from 'vue'
import EP, { ElDialog } from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import FieldConfigDialog from '/src/components/smart/panels/FieldConfigDialog.vue'
import { anchoredDialogAttrs, useButtonAnchoredDialog } from '/src/smart/utils/anchorDialog.js'
import { vPanelDrag } from '/src/smart/utils/panelDrag.js'
createApp({setup() {
  const openKey=ref(0), visible=ref(false), kind=ref('field'), body=ref(null), name=ref('编组'), at=ref(null)
  const place=useButtonAnchoredDialog(()=>body.value,()=>at.value,()=>visible.value && kind.value==='group',()=>openKey.value)
  window.openPanel=(value,point={x:900,y:680})=>{openKey.value++;kind.value=value;at.value=point;visible.value=true}
  window.moveAnchor=point=>{at.value=point}
  return ()=>kind.value==='field'
    ? h(FieldConfigDialog,{openKey:openKey.value,visible:visible.value,at:at.value,field:{label:'字段',field_type:'text',options:{}},onClose:()=>visible.value=false})
    : h(ElDialog,{transition:{css:false},...anchoredDialogAttrs(at.value,320,250),modelValue:visible.value,width:320,title:'修改编组',onOpened:place},
      {default:()=>withDirectives(h('div',{ref:body},[
        h('div',{'data-panel-drag-handle':'',style:'height:20px'},'拖动'),
        h('input',{value:name.value,onInput:e=>name.value=e.target.value}),
        h('span',{},name.value),
      ]),[[vPanelDrag,{panel:'.el-dialog'}]])})
}}).use(EP).mount('#app')
`
const server=await createServer({server:{host:'127.0.0.1',port:0},plugins:[{
  name:'dialog-position-review',resolveId(id){if(id==='/__position.js')return id},load(id){if(id==='/__position.js')return code},
  configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__position')return next();res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__position.js"></script>')})},
}]})
await server.listen()
const browser=await chromium.launch()
try {
  const page=await browser.newPage({viewport:{width:1000,height:800}})
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__position`)
  await page.waitForFunction(()=>!!window.openPanel)
  for(const kind of ['field','group']) {
    await page.evaluate(kind=>window.openPanel(kind),kind)
    const panel=page.locator('.el-dialog:visible')
    await panel.waitFor()
    await page.waitForTimeout(400)
    const original=await panel.boundingBox()
    const input=panel.locator('input').first()
    await input.click()
    await input.fill('新名称')
    await page.waitForTimeout(100)
    const edited=await panel.boundingBox()
    assert.equal(edited.x,original.x,kind+' input x')
    assert.equal(edited.y,original.y,kind+' input y')
    const handle=panel.locator('[data-panel-drag-handle]')
    await handle.click()
    const clicked=await panel.boundingBox()
    assert.equal(clicked.x,edited.x,kind+' handle x')
    assert.equal(clicked.y,edited.y,kind+' handle y')
    const box=await handle.boundingBox()
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2)
    await page.mouse.down()
    await page.mouse.move(box.x+box.width/2-60,box.y+box.height/2+30,{steps:5})
    await page.mouse.up()
    const dragged=await panel.boundingBox()
    assert.ok(dragged.x<clicked.x-40,kind+' still draggable')
    await input.fill('拖动后编辑')
    await page.waitForTimeout(100)
    assert.equal((await panel.boundingBox()).x,dragged.x,kind+' preserves drag after edit')
    await page.evaluate(()=>window.moveAnchor({x:140,y:100}))
    await page.waitForTimeout(100)
    assert.equal((await panel.boundingBox()).x,144,kind+' new anchor clears dragged position')
    await input.fill('切换后编辑')
    await page.waitForTimeout(100)
    assert.equal((await panel.boundingBox()).x,144,kind+' old directive position does not return')
    const nextHandle=await handle.boundingBox()
    await page.mouse.move(nextHandle.x+20,nextHandle.y+5)
    await page.mouse.down()
    await page.mouse.move(nextHandle.x+120,nextHandle.y+45,{steps:5})
    await page.mouse.up()
    await input.evaluate(el=>{window.__previousPanelInput=el})
    await page.evaluate(kind=>window.openPanel(kind,{x:200,y:120}),kind)
    await page.waitForTimeout(450)
    assert.equal((await panel.boundingBox()).x,204,kind+' reopening resets dragged position')
    assert.ok(await input.evaluate(el=>el===window.__previousPanelInput),kind+' reuses controls on reopen')
  }
  console.log('Field and group dialogs stay fixed on input and handle clicks, and still drag correctly.')
} finally {await browser.close();await server.close()}
