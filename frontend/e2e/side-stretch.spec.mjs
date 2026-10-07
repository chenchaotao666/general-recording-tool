import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 900 } })
for (const name of ['side-1row', 'side-5row']) {
  await page.goto(pathToFileURL(join(process.env.TEMP, `fv-${name}.html`)).href)
  await page.waitForTimeout(300)
  const rows = await page.evaluate(() =>
    [...document.querySelectorAll('tr')].map((tr) => Math.round(tr.getBoundingClientRect().height)))
  console.log(name, JSON.stringify(rows))
  await (await page.$('.page')).screenshot({ path: `e2e/out-${name}.png` })
}
await browser.close()
