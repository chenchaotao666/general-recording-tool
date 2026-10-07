import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const file = join(process.env.TEMP, 'out-half.html')
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 700 } })
await page.goto(pathToFileURL(file).href)
await page.waitForTimeout(400)
const pages = await page.$$('.page')
await pages[pages.length - 1].screenshot({ path: 'e2e/out-half-last.png' })
await browser.close()
console.log('done')
