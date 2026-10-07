import { chromium } from 'playwright'
import { readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const base = resolve('../docs/打印模板/_renders')
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 700 } })
let n = 0
for (const dir of readdirSync(base, { withFileTypes: true })) {
  if (!dir.isDirectory()) continue
  for (const f of readdirSync(join(base, dir.name)).filter((x) => x.endsWith('.html'))) {
    const p = join(base, dir.name, f)
    await page.goto(pathToFileURL(p).href)
    await page.waitForTimeout(150)
    const el = await page.$('.page')
    await el.screenshot({ path: p.replace(/\.html$/, '.png') })
    n++
  }
}
await browser.close()
console.log('截图', n, '张')
