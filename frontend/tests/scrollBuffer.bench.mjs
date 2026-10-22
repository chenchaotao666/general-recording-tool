// Diagnostic only: inject a benchmark hook through Vite; production files stay unchanged.
// Run: node tests/scrollBuffer.bench.mjs
import { createServer } from 'vite'
import { chromium } from 'playwright'
import { writeFileSync, mkdirSync } from 'node:fs'

const wide = Number(process.env.BENCH_WIDE || 35)
const throttles = (process.env.BENCH_CPU || '1').split(',').map(Number)
const fixture = `import {createApp,h} from 'vue';import EP from 'element-plus';import VXE from 'vxe-table';
import 'element-plus/dist/index.css';import 'vxe-table/lib/style.css';import '/src/smart/tokens.css';import '/src/smart/scrollbars.css';
import Grid from '/src/components/smart/grid/SmartGrid.vue';
const opts=Array.from({length:5},(_,i)=>({id:'o'+i,label:['VIP','Important','Customer','Review','Follow up'][i],color:'blue'}));
const fields=Array.from({length:60},(_,i)=>({field_name:'f'+i,field_type:i%3?'multiSelect':'text',label:'Field '+i,options:{options:opts}}));
const rows=Array.from({length:5000},(_,i)=>Object.fromEntries([['id',i+1],['__key',String(i+1)],...fields.map((f,j)=>[f.field_name,j%3?['o0','o1','o2','o3']:('Record '+i+' column '+j)])]));
createApp({render:()=>h(Grid,{fields,rows,height:600})}).use(EP).use(VXE).mount('#app');`
const hook = `
onMounted(() => { columnBuffer.vertical = () => {}; columnBuffer.horizontal = () => {}; window.__bufferBench = {
 get table() { return gridRef.value },
 async configOnly(preSize, oSize = preSize) { virtualXConfig.value = {enabled:true,gt:0,preSize,oSize}; await nextTick() },
 async size(preSize, oSize = preSize) {
  virtualXConfig.value = {enabled:true,gt:0,preSize,oSize};
  const table=gridRef.value, s=table.internalData.scrollXStore;
  const first=s.visibleStartIndex+1;
  s.preloadSize=preSize; s.offsetSize=oSize;
  s.startIndex=Math.max(0,first-1-preSize-oSize); s.endIndex=first+s.visibleSize+preSize+oSize;
  await table.updateScrollXData();
 },
 snapshot() { return {store:{...gridRef.value.internalData.scrollXStore},
  cells:document.querySelectorAll('td.vxe-body--column').length,
  tags:document.querySelectorAll('.compact-tag').length,
  elements:document.querySelectorAll('.smart-vxe *').length,
  left:gridRef.value.getScroll().scrollLeft,top:gridRef.value.getScroll().scrollTop} }
} })
`
const server = await createServer({ server: { port: 5186 }, plugins: [{
 name:'buffer-bench', enforce:'pre',
 resolveId(id) { if(id==='/__buffer.js') return id },
 load(id) { if(id==='/__buffer.js') return fixture },
 transform(source,id) {
  if(!id.replaceAll('\\','/').endsWith('/smart/grid/SmartGrid.vue')) return
  const original='const virtualXConfig = ref({ enabled: true, gt: 0, preSize: WIDE_COLUMN_BUFFER, oSize: WIDE_COLUMN_BUFFER })'
  if(!source.includes(original)) throw Error('Benchmark hook no longer matches SmartGrid')
  return source.replace(original,`const virtualXConfig = ref({ enabled: true, gt: 0, preSize: ${wide}, oSize: ${wide} })`).replace('</script>',hook+'</script>')
 },
 configureServer(s) { s.middlewares.use((req,res,next)=>{
  if(req.url!=='/__buffer') return next()
  res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/__buffer.js"></script>')
 }) },
}] })
await server.listen()
const browser = await chromium.launch()
const results=[]
let configProbe
try {
 for(const throttle of throttles) {
  for(let round=0;round<3;round++) {
   // Alternate order to reduce warm-up/order bias. Each run gets a fresh page/cache.
   for(const mode of [['fixed','narrow3','narrow12'],['narrow12','fixed','narrow3'],['narrow3','narrow12','fixed']][round]) {
    const page=await browser.newPage({viewport:{width:1200,height:760}})
    const errors=[];page.on('pageerror',e=>errors.push(e.message))
    const cdp=await page.context().newCDPSession(page)
    await cdp.send('Performance.enable')
    await page.goto(server.resolvedUrls.local[0]+'__buffer')
    await page.waitForFunction(()=>window.__bufferBench?.table)
    await page.evaluate(()=>window.__bufferBench.table.scrollTo(3200,3600))
    await page.waitForTimeout(450)
    if(!configProbe) {
     configProbe=await page.evaluate(async(wide)=>{
      const b=window.__bufferBench,before=b.snapshot();await b.configOnly(1,2);const after=b.snapshot();await b.configOnly(wide);return{before,after}
     },wide)
    }
    await page.evaluate(wide=>window.__bufferBench.size(wide),wide)
    await page.waitForTimeout(200)
    const before=await page.evaluate(()=>window.__bufferBench.snapshot())
    await cdp.send('Emulation.setCPUThrottlingRate',{rate:throttle})
    const metricsBefore=await cdp.send('Performance.getMetrics')
    const thumb=await page.locator('.st-vertical-thumb').boundingBox()
    await page.mouse.move(thumb.x+thumb.width/2,thumb.y+thumb.height/2)
    await page.mouse.down()
    await page.evaluate(async({mode,startY,wide})=>{
     const b=window.__bufferBench,track=document.querySelector('.st-vertical-track');
     const frames=[],longTasks=[];let previous=performance.now(),phase='drag';
     const observer=new PerformanceObserver(list=>list.getEntries().forEach(e=>longTasks.push({start:e.startTime,duration:e.duration})))
     observer.observe({type:'longtask'})
     let running=true
     function frame(time){if(!running)return;frames.push({phase,dt:time-previous});previous=time;requestAnimationFrame(frame)}
     requestAnimationFrame(frame)
     const switchStart=performance.now()
     if(mode==='narrow3')await b.size(3)
     if(mode==='narrow12')await b.size(1,2)
     const switchMs=performance.now()-switchStart,during=b.snapshot()
     const start=performance.now(),duration=2400
     await new Promise(resolve=>{
      function move(time){
       const p=Math.min(1,(time-start)/duration)
       track.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,cancelable:true,pointerId:1,buttons:1,clientY:startY+p*180,clientX:1000}))
       if(p<1)requestAnimationFrame(move);else resolve()
      }
      requestAnimationFrame(move)
     })
     phase='settle';window.__finishBench=async()=>{
      await new Promise(r=>setTimeout(r,200));const t=performance.now()
      if(mode!=='fixed')await b.size(wide)
      const restoreMs=performance.now()-t
      await new Promise(r=>setTimeout(r,350));running=false;observer.disconnect()
      return{frames,longTasks,switchMs,restoreMs,during,after:b.snapshot()}
     }
    },{mode,startY:thumb.y+thumb.height/2,wide})
    await page.mouse.up()
    const data=await page.evaluate(()=>window.__finishBench())
    const metricsAfter=await cdp.send('Performance.getMetrics')
    const m=Object.fromEntries(metricsBefore.metrics.map(x=>[x.name,x.value]))
    const metrics=Object.fromEntries(metricsAfter.metrics.filter(x=>['TaskDuration','ScriptDuration','LayoutDuration','RecalcStyleDuration','LayoutCount','RecalcStyleCount'].includes(x.name)).map(x=>[x.name,x.value-m[x.name]]))
    const stats=phase=>{
     const values=data.frames.filter(x=>x.phase===phase).map(x=>x.dt).sort((a,b)=>a-b)
     return{count:values.length,p95:values[Math.floor(values.length*.95)],max:values.at(-1),over25:values.filter(x=>x>25).length}
    }
    const result={throttle,round,mode,before,during:data.during,after:data.after,switchMs:data.switchMs,restoreMs:data.restoreMs,drag:stats('drag'),settle:stats('settle'),longTasks:data.longTasks,metrics,errors}
    results.push(result)
    console.log(JSON.stringify({throttle,round,mode,cells:data.during.cells,tags:data.during.tags,drag:result.drag,taskMs:metrics.TaskDuration*1000,switchMs:data.switchMs,restoreMs:data.restoreMs,errors}))
    if(data.after.top<=before.top||data.after.left!==before.left||errors.length)throw Error('Invalid scrolling benchmark')
    await page.close()
   }
  }
 }
} finally {
 mkdirSync('../docs/benchmarks',{recursive:true})
 writeFileSync(`../docs/benchmarks/scroll-buffer-${wide}-1-2.json`,JSON.stringify({date:new Date().toISOString(),environment:{wide,variants:['fixed','narrow3','narrow12'],browser:browser.version(),viewport:'1200x760',rows:5000,columns:60,durationMs:2400,note:'Headless Chromium dev build; simulated captured thumb movement, x scroll=3200; 2/3 columns multi-select; CPU throttle is synthetic.'},configProbe,results},null,2))
 await browser.close();await server.close()
}
