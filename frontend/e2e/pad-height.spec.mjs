import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 1000 } })
await page.goto(pathToFileURL('C:/Users/Administrator/AppData/Local/Temp/fv-1row-half.html').href)
await page.waitForTimeout(300)
const rows = await page.evaluate(() =>
  [...document.querySelectorAll('tr')].map((tr) => ({
    h: Math.round(tr.getBoundingClientRect().height),
    txt: (tr.textContent || '').replace(/ /g, '').slice(0, 14),
  })))
rows.forEach((r, i) => console.log(i, r.h, JSON.stringify(r.txt)))
await browser.close()
