// 思维导图存储格式（引擎无关中间格式）：{ text: string, children: [...] }
// 引擎已定型 simple-mind-map，保留抽象便于以后替换/扩展

// RichText 插件开启后节点 text 是 HTML（如 <p>分支A</p>）；中间格式存纯文本
export function htmlToText(html) {
  if (!html) return ''
  if (!/<[a-z]/i.test(html)) return html
  const div = document.createElement('div')
  div.innerHTML = html
  return (div.innerText || '').replace(/\s+$/, '')
}

// ---------- simple-mind-map：{ data: { text }, children: [] } ----------
export function simpleToCanonical(node) {
  return {
    text: htmlToText(node?.data?.text ?? ''),
    children: (node?.children || []).map(simpleToCanonical),
  }
}

export function canonicalToSimple(node) {
  return {
    data: { text: node?.text ?? '' },
    children: (node?.children || []).map(canonicalToSimple),
  }
}
