import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
 const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
 await page.route('**/api/smart/ai/scenes', route => route.fulfill({ json: { categories: [], scenes: [{ key: 'custom', label: 'Custom', input: 'multi' }] } }))
 await page.goto('http://localhost:5173')
 await page.evaluate(async () => {
   const { createApp } = await import('/node_modules/.vite/deps/vue.js')
   const { default: ElementPlus } = await import('/node_modules/.vite/deps/element-plus.js')
   const { default: Panel } = await import('/src/components/smart/ai/AiFieldPanel.vue')
   const root = document.createElement('div'); document.body.replaceChildren(root)
   createApp(Panel, { tableId: 1, x: 900, y: 50, fields: [{ field_name: 'name', label: 'Source', field_type: 'text' }], rows: [{ name: 'Example' }] }).use(ElementPlus).mount(root)
 })
 await page.locator('.afe').waitFor()
 for (const size of [{ width: 1280, height: 800 }, { width: 390, height: 700 }]) {
   await page.setViewportSize(size)
   await page.waitForTimeout(200)
   const box = await page.locator('.afe').boundingBox()
   assert.ok(box.x >= 0 && box.x + box.width <= size.width + 1)
   assert.ok(box.y >= 0 && box.y + box.height <= size.height + 1)
   await page.locator('.afe-btn.primary').scrollIntoViewIfNeeded()
   assert.ok(await page.locator('.afe-btn.primary').isVisible())
 }
 await page.setViewportSize({ width: 1280, height: 800 })
 await page.screenshot({ path: 'tests/ai-field-unified-preview.png' })
 console.log('Desktop and mobile panel bounds passed')
} finally { await browser.close() }
