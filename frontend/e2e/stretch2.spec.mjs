import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 900 } })
await page.goto(pathToFileURL(join(process.env.TEMP, 'fv-stretch.html')).href)
await page.waitForTimeout(300)
const rows = await page.evaluate(() =>
  [...document.querySelectorAll('tr')].map((tr) => Math.round(tr.getBoundingClientRect().height)))
console.log('rows:', JSON.stringify(rows))
await browser.close()
