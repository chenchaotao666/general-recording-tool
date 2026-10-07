import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 700 } })
await page.goto(pathToFileURL(join(process.env.TEMP, 'fv-logo.html')).href)
await page.waitForTimeout(400)
const img = await page.evaluate(() => {
  const el = document.querySelector('.page img')
  return el ? { w: el.getBoundingClientRect().width, naturalW: el.naturalWidth, x: Math.round(el.getBoundingClientRect().x), y: Math.round(el.getBoundingClientRect().y) } : null
})
console.log('img:', JSON.stringify(img))
await (await page.$('.page')).screenshot({ path: 'e2e/out-logo.png' })
await browser.close()
console.log(img && img.naturalW > 0 ? 'PASS' : 'FAIL')
