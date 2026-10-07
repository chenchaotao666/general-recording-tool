import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const DIR = 'C:/Users/Administrator/AppData/Local/Temp'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 900, height: 1000 } })
for (const p of ['a4', 'half', 'third']) {
  await page.goto(pathToFileURL(join(DIR, `fv-${p}.html`)).href)
  await page.waitForTimeout(300)
  const m = await page.evaluate(() => {
    const pg = document.querySelector('.page')
    const t = document.querySelector('table')
    const rows = [...document.querySelectorAll('tr')].map((tr) => Math.round(tr.getBoundingClientRect().height))
    // 明细数据行 vs 补空行高度（序号1行 vs 合计前一行）
    return {
      pageH: Math.round(pg.getBoundingClientRect().height),
      tableW: Math.round(t.getBoundingClientRect().width),
      dataRowH: rows[7] ?? null,          // 明细第一行
      padRowH: rows[rows.length - 6] ?? null,  // 合计前的补空行
    }
  })
  console.log(p, JSON.stringify(m))
  await (await page.$('.page')).screenshot({ path: `e2e/out-paper2-${p}.png` })
}
await browser.close()
