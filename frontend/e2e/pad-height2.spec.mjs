import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 900 } })
await page.goto(pathToFileURL(join(process.env.TEMP, 'fv-pad.html')).href)
await page.waitForTimeout(300)
const rows = await page.evaluate(() =>
  [...document.querySelectorAll('tr')].map((tr) => Math.round(tr.getBoundingClientRect().height)))
console.log('rows:', JSON.stringify(rows))
const uniq = [...new Set(rows)]
console.log('行高种类:', uniq, uniq.length <= 2 ? 'PASS(补空行与内容行等高)' : 'FAIL')
await browser.close()
