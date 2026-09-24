// 验证：> 空格 → 折叠块；点击箭头折叠/展开；保存数据结构正确
import { chromium } from 'playwright'

const BASE = 'http://localhost:5175'
const results = []
const browser = await chromium.launch()
const page = await browser.newPage()

const login = await page.request.post(`${BASE}/api/auth/login`, {
  data: { username: 'admin', password: 'admin123' },
})
const { token, user } = await login.json()
await page.goto(`${BASE}/login`)
await page.evaluate(([t, u]) => {
  localStorage.setItem('grt_token', t)
  localStorage.setItem('grt_user', JSON.stringify(u))
}, [token, user])
await page.goto(`${BASE}/notes`)
await page.waitForSelector('.notes-page')

await page.click('.side-top .el-button--primary')
await page.waitForSelector('.editor-holder .ce-paragraph')
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.type('>')
await page.keyboard.press(' ')
await page.waitForTimeout(300)
await page.keyboard.type('折叠标题')
await page.waitForTimeout(200)

async function dump(label) {
  const d = await page.evaluate(() => {
    const t = document.querySelector('.toggle-block')
    const body = document.querySelector('.toggle-body')
    return {
      hasToggle: !!t,
      collapsed: t?.classList.contains('collapsed'),
      bodyVisible: body ? getComputedStyle(body).display !== 'none' : null,
      arrowText: document.querySelector('.toggle-arrow')?.textContent,
      titleText: document.querySelector('.toggle-title')?.textContent,
      quoteCaptionVisible: !![...document.querySelectorAll('.cdx-quote__caption')].filter((e) => getComputedStyle(e).display !== 'none').length,
    }
  })
  results.push({ label, ...d })
}

await dump('D1: >空格转换后')

// 点击 body 输入内容（先点开 toggle-body）
await page.click('.toggle-body')
await page.keyboard.type('折叠里面的内容')
await page.waitForTimeout(200)
await dump('D2: 输入内容后')

// 点击箭头折叠
await page.click('.toggle-arrow')
await page.waitForTimeout(200)
await dump('D3: 点击箭头折叠')

// 再点击展开
await page.click('.toggle-arrow')
await page.waitForTimeout(200)
await dump('D4: 再点击展开')

// 等自动保存后检查保存到后端的数据
await page.waitForTimeout(1600)
const tree = await page.request.get(`${BASE}/api/notes/tree`, {
  headers: { Authorization: `Bearer ${token}` },
})
const notes = (await tree.json()).notes
const latest = notes[0]
const detail = await page.request.get(`${BASE}/api/notes/${latest.id}`, {
  headers: { Authorization: `Bearer ${token}` },
})
const saved = (await detail.json()).blocks
results.push({ label: 'D5: 保存到后端的块', blocks: saved.map((b) => ({ type: b.type, data: b.data })) })

console.log(JSON.stringify(results, null, 2))
await browser.close()
