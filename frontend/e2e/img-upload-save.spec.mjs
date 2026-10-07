// 真实 UI：上传带图 xlsx → 保存 → 检查落盘文件是否带图 → 预览是否显示
import { chromium } from 'playwright'
import { join } from 'node:path'

const BASE = 'http://localhost:5175'
const UPLOAD_FILE = 'C:/Users/Administrator/AppData/Local/Temp/tmps4v4bafl/logo-upload.xlsx'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e).slice(0, 120)))

const login = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const { token, user } = await login.json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => {
  localStorage.setItem('grt_token', t)
  localStorage.setItem('grt_user', JSON.stringify(u))
}, [token, user])
await page.goto(`${BASE}/t/35`)
await page.waitForSelector('button:has-text("打印")')
await page.click('button:has-text("打印")')
await page.waitForSelector('.tpl-table tbody tr')
// 编辑 cccc（模板 8）
await page.click('.tpl-table tbody tr:has-text("cccc") button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)

// 上传带图 xlsx
const fileInput = await page.$('.bar-ops .el-upload input[type=file]')
await fileInput.setInputFiles(UPLOAD_FILE)
await page.waitForTimeout(3000)

// 保存
await page.click('.pt-designer button:has-text("保存")')
await page.waitForTimeout(3000)

// 检查落盘文件图片
const hasImg = await page.request.get(`${BASE}/api/print-templates/8/excel?token=${token}`).then(async (r) => {
  const buf = await r.body()
  return buf.includes(Buffer.from('media/').toString()) || buf.includes(Buffer.from('image').toString())
})
console.log('落盘文件含图片:', hasImg ? 'PASS' : 'FAIL')

// 预览
await page.click('button:has-text("打印")')
await page.waitForSelector('.tpl-table tbody tr')
await page.click('.tpl-table tbody tr:has-text("cccc") button:has-text("预览")')
await page.waitForSelector('.pv-frame', { timeout: 30000 })
await page.waitForTimeout(1500)
const imgShown = await page.evaluate(() => {
  const f = document.querySelector('.pv-frame')
  const imgs = f?.contentDocument?.querySelectorAll('.page img')
  return imgs?.length > 0
})
console.log('预览显示图片:', imgShown ? 'PASS' : 'FAIL')
await page.screenshot({ path: 'e2e/out-img-preview.png' })
await browser.close()
