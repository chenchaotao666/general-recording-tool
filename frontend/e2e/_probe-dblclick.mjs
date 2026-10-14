// 探针：真人节奏双击（间隔 250/350/450ms）观察选中态闪现时长
import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const loginRes = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const login = await loginRes.json()
await page.addInitScript(([token, user]) => {
  localStorage.setItem('grt_token', token)
  localStorage.setItem('grt_user', JSON.stringify(user))
  localStorage.setItem('grt_tenant_id', String(user.tenant?.id || user.tenant_id || ''))
  sessionStorage.setItem('grt_tenant_picked', '1')
}, [login.token, login.user])

await page.goto(`${BASE}/smart`, { waitUntil: 'networkidle' })
await page.waitForSelector('.smart-home', { timeout: 10000 })
await page.getByText('⊞ 工作表').click()
await page.fill('.el-message-box input', `双击节奏${Date.now() % 100000}`)
await page.locator('.el-message-box button.el-button--primary').click()
await page.waitForURL(/\/smart\/table\/\d+/, { timeout: 10000 })
await page.waitForSelector('.smart-vxe .vxe-body--row', { timeout: 10000 })
await page.waitForTimeout(1200)

// 注入监听器：记录 cell-selected / cell-editing 出现与消失的时间线
await page.evaluate(() => {
  window.__timeline = []
  const t0 = performance.now()
  const cls = () => ({
    sel: !!document.querySelector('td.cell-selected'),
    edit: !!document.querySelector('td.cell-editing'),
  })
  let prev = cls()
  new MutationObserver(() => {
    const cur = cls()
    if (cur.sel !== prev.sel || cur.edit !== prev.edit) {
      window.__timeline.push({ t: Math.round(performance.now() - t0), ...cur })
      prev = cur
    }
  }).observe(document.querySelector('.smart-vxe'), { subtree: true, attributes: true, attributeFilter: ['class'], childList: true })
})

const numCell = page.locator('.smart-vxe .vxe-body--row:visible:not(.row-add)').first().locator('td:visible').nth(5)
for (const gap of [250, 350, 450]) {
  await page.evaluate(() => { window.__timeline = [] })
  await numCell.dblclick({ delay: gap })   // delay = 两次点击间隔（会正确触发 dblclick 事件）
  await page.waitForTimeout(600)
  const tl = await page.evaluate(() => window.__timeline)
  // 计算选中态持续了多久
  let flash = 0
  for (let i = 0; i < tl.length; i++) {
    if (tl[i].sel && !tl[i].edit) {
      const end = tl.slice(i + 1).find(e => !e.sel || e.edit)
      flash = end ? end.t - tl[i].t : 999
      break
    }
  }
  console.log(`双击间隔 ${gap}ms: 时间线 =`, JSON.stringify(tl), `| 选中态闪现 ${flash}ms`)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)
}
await browser.close()
