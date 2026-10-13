// 回归：drawio 保存内容后刷新，编辑器内部画布尺寸不能塌陷（对比刷新前后 .geDiagramContainer 尺寸）
import { chromium } from 'playwright'
const BASE = 'http://localhost:5190'
const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  proxy: { server: 'http://127.0.0.1:7897', bypass: 'localhost,127.0.0.1' },
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36',
})
const page = await ctx.newPage()
const login = await page.request.post(`${BASE}/api/auth/login`, { data: { username: 'admin', password: 'admin123' } })
const { token, user } = await login.json()
const headers = { Authorization: `Bearer ${token}` }
const xml = '<mxfile><diagram name="p1"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="2" value="测试" style="rounded=1;" vertex="1" parent="1"><mxGeometry x="200" y="200" width="120" height="60" as="geometry"/></mxCell></root></mxGraphModel></diagram></mxfile>'
const created = await (await page.request.post(`${BASE}/api/whiteboards`, {
  headers, data: { title: '尺寸复现2', engine: 'drawio', content: JSON.stringify({ xml }) },
})).json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => { localStorage.setItem('grt_token', t); localStorage.setItem('grt_user', JSON.stringify(u)) }, [token, user])

async function measure(tag) {
  // 就绪信号 = iframe 里的画布容器出现且有尺寸（轮询，覆盖冷启动慢的情况）
  let inner = null
  for (let i = 0; i < 45 && !inner; i++) {
    await page.waitForTimeout(1000)
    const frame = page.frames().find((f) => f.url().includes('diagrams.net'))
    if (frame) {
      inner = await frame.evaluate(() => {
        const r = document.querySelector('.geDiagramContainer')?.getBoundingClientRect()
        return r && r.width > 10 ? [Math.round(r.width), Math.round(r.height)] : null
      }).catch(() => null)
    }
  }
  console.log(tag, 'inner canvas:', JSON.stringify(inner))
  await page.screenshot({ path: `e2e/out-drawio-${tag}.png` })
  return inner
}

await page.goto(`${BASE}/whiteboard?wbId=${created.id}`)
const a = await measure('fresh')
await page.reload()
const b = await measure('after-reload')
await page.request.delete(`${BASE}/api/whiteboards/${created.id}`, { headers })
await browser.close()
console.log(a && b && Math.abs(a[0] - b[0]) < 20 && a[0] > 400 ? 'PASS' : 'FAIL')
