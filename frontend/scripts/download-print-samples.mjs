// 从 yc620.com 图片展示页按行业分类下载打印模板样图 → ../docs/打印模板/<行业>/<标题>.jpg
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const BASE = 'https://www.yc620.com'
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0' }
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'docs', '打印模板')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function getText(url) {
  const res = await fetch(url, { headers: UA })
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.text()
}

async function getBuf(url) {
  const res = await fetch(url, { headers: UA })
  if (!res.ok) return null
  return Buffer.from(await res.arrayBuffer())
}

// 1) 主页面解析行业分类（链接 + 名称）
const main = await getText(`${BASE}/yc/picture/`)
const cats = [...main.matchAll(/href="\/yc\/picture\/([^"/]+)\/"[^>]*>([^<]{2,20})<\/a>/g)]
  .map((m) => ({ code: m[1], name: m[2].trim() }))
  .filter((c, i, arr) => arr.findIndex((x) => x.code === c.code) === i)
console.log(`分类 ${cats.length} 个:`, cats.map((c) => c.name).join('、'))

let total = 0, ok = 0, fail = []
for (const cat of cats) {
  const html = await getText(`${BASE}/yc/picture/${cat.code}/`)
  await sleep(150)
  // 列表项：data-original=真实图 alt=标题（href/title 与之等价，alt 更全）
  const items = [...html.matchAll(/data-original="?\s*([^"\s>]+)"?[^>]*alt="([^"]+)"/g)]
    .map((m) => ({ src: m[1], title: m[2].trim() }))
  const seen = new Set()
  const dir = join(OUT, cat.name)
  await mkdir(dir, { recursive: true })
  for (const it of items) {
    const hnum = (it.title.match(/[Hh]\d{3,}/) || [])[0]
    const dirName = (it.src.match(/UploadFiles\/([^/"]+)\//) || [])[1]
    // 站点前几条常把图片错指到同一张，按标题编号拼真实路径；拼不出才退回原链接
    const url = dirName && hnum
      ? `${BASE}/uploads/UploadFiles/${dirName}/${hnum.toUpperCase()}.jpg`
      : (it.src.startsWith('http') ? it.src : `${BASE}/${it.src.replace(/^\//, '')}`)
    let name = `${it.title.replace(/[\\/:*?"<>|]/g, '')}.jpg`
    if (seen.has(name)) continue
    seen.add(name)
    const buf = await getBuf(url)
    await sleep(120)
    if (buf && buf.length > 3000 && buf[0] === 0xff && buf[1] === 0xd8) {
      await writeFile(join(dir, name), buf)
      ok++
    } else {
      fail.push(`${cat.name}/${name} (${url})`)
    }
    total++
  }
  console.log(`${cat.name}: ${seen.size} 张`)
}
console.log(`\n完成 ${ok}/${total}，失败 ${fail.length}`)
if (fail.length) console.log(fail.join('\n'))
