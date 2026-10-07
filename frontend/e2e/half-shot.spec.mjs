import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const file = join(process.env.TEMP, 'out-half.html')
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 800 } })
await page.goto(pathToFileURL(file).href)
await page.waitForTimeout(400)
await (await page.$('.page')).screenshot({ path: 'e2e/out-half-padded.png' })
await browser.close()
console.log('done')
