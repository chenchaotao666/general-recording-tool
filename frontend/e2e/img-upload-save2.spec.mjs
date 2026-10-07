// 调试：上传带图 xlsx → 保存，抓网络请求看 /excel 与 /excel-json 是否都发生
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const UPLOAD_FILE = 'C:/Users/Administrator/AppData/Local/Temp/tmps4v4bafl/logo-upload.xlsx'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e).slice(0, 120)))

const requests = []
page.on('request', (r) => {
  if (/\/print-templates\/\d+\/excel/.test(r.url())) requests.push(`${r.method()} ${r.url().split('?')[0]}`)
})
page.on('response', async (r) => {
  if (/\/print-templates\/\d+\/excel/.test(r.url())) {
    requests.push(`  → ${r.status()}`)
  }
})

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
await page.click('.tpl-table tbody tr:has-text("cccc") button:has-text("编辑")')
await page.waitForSelector('#ptSheetBox .luckysheet', { timeout: 30000 })
await page.waitForTimeout(2500)

// 上传：找 el-upload 的 input
const inputs = await page.evaluate(() =>
  [...document.querySelectorAll('.pt-designer input[type=file]')].length)
console.log('file inputs:', inputs)

const fileInput = await page.$('.pt-designer .el-upload input[type=file]')
if (fileInput) {
  await fileInput.setInputFiles(UPLOAD_FILE)
  await page.waitForTimeout(3000)
} else {
  console.log('FAIL: 找不到上传 input')
}

// 保存前看 pendingFile 状态（从 Vue 组件里不好拿，看 UI 提示）
await page.waitForTimeout(500)
await page.screenshot({ path: 'e2e/out-before-save.png' })

await page.click('.pt-designer button:has-text("保存")')
await page.waitForTimeout(3000)
console.log('请求:', JSON.stringify(requests))

// 检查落盘
const r = await page.request.get(`${BASE}/api/print-templates/8/excel?token=${token}`)
const buf = await r.body()
console.log('落盘含 media:', buf.includes(Buffer.from('xl/media/').toString()) || buf.includes(Buffer.from('media/image').toString()))
await browser.close()
