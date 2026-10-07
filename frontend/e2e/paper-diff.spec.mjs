import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'

const DIR = 'C:/Users/Administrator/AppData/Local/Temp'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 900 } })
for (const p of ['a4', 'half', 'third']) {
  await page.goto(pathToFileURL(`${DIR}/fv-${p}.html`).href)
  await page.waitForTimeout(300)
  const h = await page.evaluate(() => Math.round(document.querySelector('.page').getBoundingClientRect().height))
  await (await page.$('.page')).screenshot({ path: `e2e/out-paper-${p}.png` })
  console.log(p, '页高 px:', h)
}
await browser.close()
