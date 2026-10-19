// Run against an isolated backend: ENTERPRISE_TEST_BASE=http://127.0.0.1:5174 node e2e/light-enterprise.spec.mjs
import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import os from 'node:os'
import path from 'node:path'

const base = process.env.ENTERPRISE_TEST_BASE || 'http://127.0.0.1:5174'
const browser = await chromium.launch({ headless: true })
const errors = []
async function account(name) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const r = await context.request.post(`${base}/api/auth/register`, { data: { username: name, password: 'testing123' } })
  assert.equal(r.status(), 200)
  const session = await r.json()
  await context.addInitScript(s => {
    if (!localStorage.getItem('grt_token')) {
      localStorage.setItem('grt_token', s.token)
      localStorage.setItem('grt_user', JSON.stringify(s.user))
      localStorage.setItem('grt_tenant_id', s.user.tenant.id)
    }
    sessionStorage.setItem('grt_tenant_picked', '1')
  }, session)
  const page = await context.newPage()
  page.on('pageerror', e => errors.push(e.message))
  await page.goto(`${base}/home`)
  await page.locator('.enterprise-trigger').waitFor()
  return { context, page, session }
}
async function menu(page, name) {
  await page.locator('.enterprise-trigger').click()
  await page.getByRole('menuitem', { name, exact: true }).click()
}
async function create(page, name) {
  await menu(page, '＋ 新建企业')
  await page.getByPlaceholder('例如：星河设计工作室').fill(name)
  await page.getByRole('button', { name: '创建并进入企业', exact: true }).click()
  await page.waitForFunction(n => JSON.parse(localStorage.getItem('grt_user')).tenant.name === n, name)
  await page.locator('.enterprise-trigger').waitFor()
}
try {
  const suffix = Date.now()
  const owner = await account(`enterprise_owner_${suffix}`)
  const member = await account(`enterprise_member_${suffix}`)
  for (const title of ['基础设置', '角色管理', '组织与成员', '审计日志']) {
    assert.equal(await owner.page.locator('.aside').getByText(title, { exact: true }).count(), 0)
  }
  await create(owner.page, '星河设计工作室')
  await menu(owner.page, '我的企业 · 邀请同事')
  await owner.page.getByRole('tab', { name: '邀请同事' }).click()
  await owner.page.getByRole('button', { name: '生成邀请码', exact: true }).click()
  const codeInput = owner.page.locator('.code-box input[readonly]')
  await codeInput.waitFor()
  const code = await codeInput.inputValue()
  await owner.page.screenshot({ path: path.join(os.tmpdir(), 'grt-enterprise-invite.png') })
  await owner.page.getByRole('button', { name: '关闭', exact: true }).click()

  await menu(member.page, '加入企业')
  await member.page.getByPlaceholder('粘贴企业邀请码').fill(code)
  await member.page.getByRole('button', { name: '查看企业', exact: true }).click()
  await member.page.getByRole('button', { name: '确认加入 星河设计工作室', exact: true }).click()
  await member.page.waitForFunction(() => JSON.parse(localStorage.getItem('grt_user')).tenant.name === '星河设计工作室')
  await member.page.locator('.enterprise-trigger').waitFor()
  await menu(member.page, '我的企业 · 邀请同事')
  await member.page.getByText(`enterprise_owner_${suffix}`, { exact: true }).waitFor()
  assert.equal(await member.page.getByRole('tab', { name: '邀请同事' }).count(), 0)
  await member.page.getByRole('button', { name: '关闭', exact: true }).click()

  await create(owner.page, '星河项目二组')
  await menu(owner.page, '星河设计工作室')
  await owner.page.waitForFunction(() => JSON.parse(localStorage.getItem('grt_user')).tenant.name === '星河设计工作室')
  await owner.page.locator('.enterprise-trigger').waitFor()
  await menu(owner.page, '＋ 新建企业')
  await owner.page.getByPlaceholder('例如：星河设计工作室').waitFor()
  await owner.page.waitForTimeout(400) // 等待弹窗过渡结束后做视觉检查
  await owner.page.screenshot({ path: path.join(os.tmpdir(), 'grt-enterprise-create.png') })
  assert.deepEqual(errors, [])
  console.log('PASS: create multiple enterprises, invite, preview/join, colleague list, switch, retired menus, no browser errors')
} finally {
  await browser.close()
}
