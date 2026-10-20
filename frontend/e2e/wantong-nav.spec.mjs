import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const base = process.env.BASE_URL || 'http://localhost:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const res = await page.request.post(`${base}/api/auth/login`, { data: { username: process.env.E2E_USER || 'admin', password: process.env.E2E_PASS || 'admin123' } })
  const login = await res.json()
  assert.ok(login.token, 'Login failed')
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem('grt_token', token)
    localStorage.setItem('grt_user', JSON.stringify(user))
    localStorage.setItem('grt_tenant_id', String(user.tenant?.id || user.tenant_id || ''))
    sessionStorage.setItem('grt_tenant_picked', '1')
  }, login)

  await page.goto(`${base}/home`, { waitUntil: 'networkidle' })
  await page.locator('.nav-brand-mark').waitFor()
  assert.equal(await page.title(), '\u4e07\u901aAI\u52a9\u624b')
  for (const compact of [true, false]) {
    if (await page.locator('.aside').evaluate(el => el.classList.contains('nav-compact')) !== compact) await page.locator('.collapse-btn').click()
    await page.waitForFunction(expected => Math.round(document.querySelector('.aside').getBoundingClientRect().width) === expected, compact ? 82 : 180)
    assert.ok(await page.locator('.aside .el-menu-item').evaluateAll((items, compact) => items.every(item => {
      const icon = item.querySelector('.el-icon').getBoundingClientRect()
      const label = item.querySelector('span:not(.el-icon):not(.menu-unread)').getBoundingClientRect()
      const aligned = compact
        ? icon.bottom <= label.top + 1 && Math.abs(icon.left + icon.width / 2 - label.left - label.width / 2) < 2
        : icon.right < label.left && Math.abs(icon.top + icon.height / 2 - label.top - label.height / 2) < 2
      return aligned && Math.round(item.getBoundingClientRect().height) === (compact ? 50 : 44) && label.width <= item.clientWidth
    }), compact), 'Layout and row height must match navigation mode')
    assert.equal(await page.locator('.nav-brand-name').count(), compact ? 0 : 1)
    assert.ok(await page.locator('.el-menu-item-group__title').evaluateAll(els => els.every(el => getComputedStyle(el).fontSize === '0px' && getComputedStyle(el).borderTopWidth === '1px')))
    await page.screenshot({ path: `frontend/test-results/wantong-nav-${compact ? 'compact' : 'expanded'}.png` })
  }
  await page.locator('.aside .el-menu-item').filter({ hasText: '\u667a\u80fd\u8868' }).click()
  await page.waitForURL(/\/smart(?:\/table\/\d+|\/dashboard\/\d+)?$/)
  assert.ok((await page.locator('.aside .el-menu-item.is-active').innerText()).includes('\u667a\u80fd\u8868'))
  await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
  await page.screenshot({ path: 'frontend/test-results/wantong-login.png' })
  assert.deepEqual(errors, [])
  console.log('PASS stacked navigation, compact/expanded layouts, branding and login; no data written')
} finally {
  await browser.close()
}

