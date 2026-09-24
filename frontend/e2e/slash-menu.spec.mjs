// 验证 / 块菜单：唤起、内容、定位、过滤、Esc、方向键+Enter 插入
import { chromium } from 'playwright'

const BASE = 'http://localhost:5176'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
const fails = []
const check = (name, cond, extra = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`)
  if (!cond) fails.push(name)
}

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

// 新建页面 → 空段落输入 /
await page.click('.side-top .el-button--primary')
await page.waitForSelector('.editor-holder .ce-paragraph')
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.type('/')
await page.waitForSelector('.slash-menu', { timeout: 3000 })

// 1. 菜单项完整：11 项，含文本/标题1-3/待办/折叠块/代码块
const labels = await page.$$eval('.slash-item .slash-label', (els) => els.map((e) => e.textContent))
check('菜单 11 项', labels.length === 11, labels.join('/'))
for (const want of ['文本', '标题 1', '标题 2', '标题 3', '无序列表', '有序列表', '待办事项', '折叠块', '引用', '分割线', '代码块']) {
  check(`含「${want}」`, labels.includes(want))
}

// 2. 定位：不被左侧遮挡，完整落在视口内
const box = await page.$eval('.slash-menu', (el) => {
  const r = el.getBoundingClientRect()
  return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, iw: window.innerWidth, ih: window.innerHeight }
})
check('菜单未超出左边缘', box.left >= 0, `left=${box.left}`)
check('菜单未超出右边缘', box.right <= box.iw, `right=${box.right} iw=${box.iw}`)
check('菜单未超出下边缘', box.bottom <= box.ih, `bottom=${box.bottom} ih=${box.ih}`)

// 3. 过滤：输入 bt → 只剩 3 个标题项
await page.keyboard.type('bt')
await page.waitForTimeout(200)
const filtered = await page.$$eval('.slash-item .slash-label', (els) => els.map((e) => e.textContent))
check('过滤 bt → 3 个标题', filtered.length === 3 && filtered.every((l) => l.startsWith('标题')), filtered.join('/'))

// 4. Esc 关闭并清掉 /biao 文本
await page.keyboard.press('Escape')
await page.waitForTimeout(200)
check('Esc 后菜单关闭', (await page.$('.slash-menu')) === null)
const afterEsc = await page.$eval('.editor-holder .ce-paragraph', (el) => el.textContent)
check('Esc 后块文本已清空', afterEsc.trim() === '', JSON.stringify(afterEsc))

// 5. 方向键导航 + Enter 插入「标题 1」
await page.keyboard.type('/')
await page.waitForSelector('.slash-menu')
await page.keyboard.press('ArrowDown')  // → 标题 1
await page.keyboard.press('Enter')
await page.waitForTimeout(300)
check('Enter 插入标题 1', (await page.$('.editor-holder h1.ce-header')) !== null)
check('插入后菜单关闭', (await page.$('.slash-menu')) === null)

// 6. 鼠标点击选择「折叠块」
await page.keyboard.press('Enter')  // 标题里 Enter → 新段落
await page.waitForTimeout(200)
await page.keyboard.type('/')
await page.waitForSelector('.slash-menu')
await page.click('.slash-item:has-text("折叠块")')
await page.waitForTimeout(300)
check('点击插入折叠块', (await page.$('.editor-holder .toggle-block')) !== null)

// 7. 空格关闭菜单、文本保留（换个新页面测，避免折叠块的 Enter 行为干扰）
await page.click('.side-top .el-button--primary')
await page.waitForSelector('.editor-holder .ce-paragraph')
await page.click('.editor-holder .ce-paragraph')
await page.keyboard.type('/ab')
await page.waitForSelector('.slash-menu')
await page.keyboard.press(' ')
await page.waitForTimeout(200)
check('空格后菜单关闭', (await page.$('.slash-menu')) === null)
const afterSpace = await page.evaluate(() => {
  const ps = [...document.querySelectorAll('.ce-paragraph')]
  return ps[ps.length - 1]?.textContent || ''
})
check('空格后 /ab 文本保留', afterSpace.startsWith('/ab'), JSON.stringify(afterSpace))

console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASS')
await browser.close()
process.exit(fails.length ? 1 : 0)
