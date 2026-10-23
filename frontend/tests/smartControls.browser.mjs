// Run: node tests/smartControls.browser.mjs
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { chromium } from 'playwright'

const code = `
import { createApp, h, ref } from 'vue'
import EP, { ElInput, ElSelect, ElOption, ElInputNumber, ElDatePicker, ElButton } from 'element-plus'
import 'element-plus/dist/index.css'
import '/src/smart/tokens.css'
import ConditionValue from '/src/components/smart/panels/ConditionValue.vue'
import TbFieldSelect from '/src/components/smart/panels/TbFieldSelect.vue'
import ScheduleTimePicker from '/src/components/smart/automation/ScheduleTimePicker.vue'
import FillPanel from '/src/components/smart/panels/FillPanel.vue'
import SmartTagList from '/src/components/smart/common/SmartTagList.vue'
const fields = [{field_name:'name',label:'名称',field_type:'text'}]
createApp({setup() {
  const selected = ref(['a','b','c'])
  const text = ref('')
  const tags = ref([{value:'a',label:'产品名称'},{value:'b',label:'生产线'},{value:'c',label:'计划产量'}])
  return () => h('div', {style:'display:grid;gap:12px;width:360px;padding:24px'}, [
    h('div',{id:'tag-control',class:'st-control st-control--native st-control--wrap',style:'display:flex;width:220px;padding-inline:8px'},[
      h(SmartTagList,{items:tags.value,onRemove:value=>tags.value=tags.value.filter(t=>t.value!==value)}),
    ]),
    h('div', {id:'buttons',style:'display:flex;gap:8px'}, [
      h('button', {class:'st-button'}, '普通'),
      h(ElButton, {class:'st-button st-button--primary'}, {default:()=> '主要'}),
      h('button', {class:'st-button st-button--large'}, '取消'),
      h(ElButton, {class:'st-button st-button--large st-button--primary'}, {default:()=> '保存'}),
      h(ElButton, {class:'st-button st-button--primary',disabled:true}, {default:()=> '禁用'}),
    ]),
    ...['', ' st-control--small'].flatMap((size, i) => [
      h(ElInput, {class:'st-control'+size, id:'input'+i, placeholder:'输入内容', modelValue:text.value, 'onUpdate:modelValue':v=>text.value=v}),
      h(ElSelect, {class:'st-control'+size, id:'select'+i, modelValue:selected.value, multiple:true, collapseTags:true, collapseTagsTooltip:true,
        'onUpdate:modelValue':v=>selected.value=v}, {default:()=>['a','b','c'].map(value=>h(ElOption,{value,label:value}))}),
      h(ElInputNumber, {class:'st-control'+size, id:'number'+i, modelValue:3, controlsPosition:'right'}),
      h(ElDatePicker, {class:'st-control'+size, id:'date'+i}),
      h('input', {class:'st-control st-control--native'+size, id:'native'+i, placeholder:'原生输入'}),
    ]),
    h(ConditionValue, {field:fields[0], value:'测试', operator:'eq'}),
    h(TbFieldSelect, {fields, modelValue:'name'}),
    h(ScheduleTimePicker),
    h(ElInput, {id:'excluded', size:'large', modelValue:'未接入的单元格/详情控件'}),
    h(ElInput, {class:'st-control', id:'textarea', type:'textarea', rows:3}),
    h(FillPanel, {visible:true, fields:[{field_name:'product',label:'产品名称',field_type:'multiSelect',options:{options:[{id:'c',label:'产品C'},{id:'e',label:'产品E'}]}}],
      rules:[{fieldId:'product',operator:'contains',value:['c','e'],color:'#fceee5'}]}, {default:()=>h('button','填色')}),
  ])
}}).use(EP).mount('#app')
`
const server = await createServer({ server: {host:'127.0.0.1', port:0}, plugins:[{
  name:'smart-controls-review',
  resolveId(id) { if(id === '/__controls.js') return id },
  load(id) { if(id === '/__controls.js') return code },
  configureServer(s) { s.middlewares.use((req,res,next)=>{
    if(req.url !== '/__controls') return next()
    res.setHeader('Content-Type','text/html')
    res.end('<div id="app"></div><script type="module" src="/__controls.js"></script>')
  }) },
}]})
await server.listen()
const browser = await chromium.launch()
try {
  const page = await browser.newPage({viewport:{width:1100,height:1000}})
  const errors = []
  page.on('pageerror', e=>errors.push(e.message))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__controls`)
  await page.locator('.tbfs').first().waitFor()
  await page.locator('.flp').waitFor()
  await page.waitForTimeout(300)
  const tags = await page.locator('.st-tag-list__item').evaluateAll(ns=>ns.map(n=>({height:n.getBoundingClientRect().height,top:n.getBoundingClientRect().top})))
  assert.ok(tags.every(t=>t.height===24))
  assert.ok(tags[2].top>tags[0].top, 'tags wrap to another row')
  const tagHeight = await page.locator('#tag-control').evaluate(n=>n.getBoundingClientRect().height)
  assert.ok(tagHeight>32, 'selector expands with tags')
  await page.getByRole('button',{name:'移除计划产量',exact:true}).click()
  assert.equal(await page.locator('.st-tag-list__item').count(),2)
  assert.equal(await page.locator('#tag-control').evaluate(n=>n.getBoundingClientRect().height),32)
  const buttonStyles = await page.locator('.st-button').evaluateAll(ns=>ns.filter(n=>n.getBoundingClientRect().height).map(n=>({
    height:n.getBoundingClientRect().height, expected:n.classList.contains('st-button--large')?36:28,
    color:getComputedStyle(n).backgroundColor, expectedColor:n.classList.contains('st-button--primary')?'rgb(38, 126, 240)':'rgb(242, 243, 245)',
  })))
  for (const item of buttonStyles) { assert.equal(item.height,item.expected); assert.equal(item.color,item.expectedColor) }
  await page.locator('#buttons').screenshot({path:'../docs/smart-buttons-review.png'})
  await page.locator('.flp').screenshot({path:'../docs/smart-fill-controls-review.png'})
  assert.equal(await page.locator('.flp .el-select__placeholder').innerText(), '包含')
  await page.locator('.flp-val').evaluate(n=>{n.style.flex='0 0 100px';n.style.width='100px'})
  await page.waitForTimeout(100)
  assert.match(await page.locator('.flp .smt-content .smt-count').innerText(), /^\+[12]$/)
  await page.locator('.flp .enum-val').click()
  await page.waitForTimeout(100)
  assert.equal(await page.locator('.flp .enum-val').evaluate(n=>getComputedStyle(n).borderTopColor),'rgb(38, 126, 240)')
  await page.locator('.flp .enum-val').click()
  await page.locator('.flp-val').evaluate(n=>{n.style.flex='0 0 350px';n.style.width='350px'})
  await page.waitForTimeout(100)
  assert.equal(await page.locator('.flp .smt-content .smt-count').count(),0)
  const heights = await page.locator('.st-control').evaluateAll(nodes=>nodes.filter(n=>!n.classList.contains('el-textarea') && !n.classList.contains('st-control--wrap') && n.getBoundingClientRect().height).map(n=>({
    className:n.className, height:n.getBoundingClientRect().height,
    expected:n.classList.contains('st-control--small')?24:32,
  })))
  for(const item of heights) assert.equal(item.height,item.expected,JSON.stringify(item))
  assert.equal(await page.locator('#excluded').evaluate(n=>n.closest('.el-input').getBoundingClientRect().height),40)
  assert.ok(await page.locator('#textarea').evaluate(n=>n.getBoundingClientRect().height)>32)
  await page.locator('#input0').fill('可正常输入')
  assert.equal(await page.locator('#input0').inputValue(),'可正常输入')
  await page.locator('.tbfs').first().click()
  await page.locator('.fpl-item:visible').first().waitFor({state:'visible'})
  await page.locator('.fpl-item:visible').first().click()
  await page.locator('.el-select').filter({has:page.locator('#select1')}).locator('.el-select__wrapper').click()
  await page.locator('.el-select-dropdown__item:visible').first().click()
  assert.deepEqual(errors,[])
  console.log(`Verified ${heights.length} controls at 32/24px, ${buttonStyles.length} buttons at 28/36px in gray/blue, input and dropdown interaction, and excluded controls.`)
} finally {
  await browser.close()
  await server.close()
}
