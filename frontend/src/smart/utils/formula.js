// 公式编辑器工具：存储形态 [field_name] ⇄ 字段胶囊、格式优化、光标所在函数（签名提示）

const isIdStart = (c) => /[A-Za-z_一-龥]/.test(c)
const isIdChar = (c) => /[A-Za-z0-9_一-龥]/.test(c)

// 公式文本 → 片段：[{t:'text', v}] | [{t:'field', field}] | [{t:'table', table}] | [{t:'tcol', table, field}]
// [引用] 按字段名或字段标题匹配；[#表ID] 整表、[#表ID.字段] 整列（tables: Map(id → {id, label, fields})）；裸 f_N 兼容旧写法
export function tokenize(formula, fields, tables = new Map()) {
  const byName = new Map(fields.map(f => [f.field_name, f]))
  const byLabel = new Map(fields.map(f => [f.label, f]))
  const out = []
  let buf = ''
  const flush = () => { if (buf) { out.push({ t: 'text', v: buf }); buf = '' } }
  const s = formula || ''
  let i = 0
  let quote = null
  while (i < s.length) {
    const c = s[i]
    if (quote) {
      buf += c
      if (c === quote) quote = null
      i++
      continue
    }
    if (c === '"' || c === "'" || c === '“') { quote = c === '“' ? '”' : c; buf += c; i++; continue }
    if (c === '[') {
      const j = s.indexOf(']', i)
      const tm = j > i ? s.slice(i + 1, j).match(/^#(\d+)(?:\.(.+))?$/) : null
      if (tm) {
        const t = tables.get(Number(tm[1])) || { id: Number(tm[1]), label: `表${tm[1]}`, fields: [] }
        flush()
        if (tm[2]) {
          const f = (t.fields || []).find(x => x.field_name === tm[2]) || { field_name: tm[2], label: tm[2], field_type: 'text' }
          out.push({ t: 'tcol', table: t, field: f })
        } else out.push({ t: 'table', table: t })
        i = j + 1
        continue
      }
      if (j > i) {
        const key = s.slice(i + 1, j).trim()
        const f = byName.get(key) || byLabel.get(key)
        if (f) { flush(); out.push({ t: 'field', field: f }); i = j + 1; continue }
      }
    }
    if (isIdStart(c) && !isIdChar(s[i - 1] || ' ')) {
      let j = i
      while (j < s.length && isIdChar(s[j])) j++
      const word = s.slice(i, j)
      if (byName.has(word) && s[j] !== '(') { flush(); out.push({ t: 'field', field: byName.get(word) }); i = j; continue }
      buf += word
      i = j
      continue
    }
    buf += c
    i++
  }
  flush()
  return out
}

// 片段 → 展示文本（[字段标题]），给只读预览与 AI 用
export function displayText(formula, fields, tables) {
  return tokenize(formula, fields, tables).map(p => (p.t === 'field' ? `[${p.field.label}]`
    : p.t === 'table' ? `[${p.table.label}]` : p.t === 'tcol' ? `[${p.table.label}.${p.field.label}]` : p.v)).join('')
}

// 公式里整表引用到的表 id（渲染胶囊前预加载这些表的字段）
export function referencedTableIds(formula) {
  return [...new Set([...(formula || '').matchAll(/\[#(\d+)/g)].map(m => Number(m[1])))]
}

// ---------- 格式优化：函数名大写、逗号后空格、运算符两侧空格；过长的嵌套调用按参数换行缩进 ----------
function lex(s) {
  const toks = []
  let i = 0
  while (i < s.length) {
    const c = s[i]
    if (/\s/.test(c)) { i++; continue }
    if (c === '"' || c === "'") {
      let j = i + 1
      while (j < s.length && s[j] !== c) j++
      toks.push({ k: 'str', v: s.slice(i, j + 1) }); i = j + 1; continue
    }
    if (c === '[') {
      const j = s.indexOf(']', i)
      toks.push({ k: 'ref', v: s.slice(i, j < 0 ? s.length : j + 1) }); i = j < 0 ? s.length : j + 1; continue
    }
    const two = s.slice(i, i + 2)
    if (['<>', '>=', '<=', '==', '!='].includes(two)) { toks.push({ k: 'op', v: two === '==' ? '=' : two === '!=' ? '<>' : two }); i += 2; continue }
    if ('+-*/&=<>%'.includes(c)) { toks.push({ k: 'op', v: c }); i++; continue }
    if ('(),.'.includes(c)) { toks.push({ k: c, v: c }); i++; continue }
    if (isIdStart(c) || /[0-9]/.test(c)) {
      let j = i
      while (j < s.length && (isIdChar(s[j]) || (s[j] === '.' && /[0-9]/.test(c)))) j++
      toks.push({ k: 'id', v: s.slice(i, j) }); i = j; continue
    }
    toks.push({ k: 'raw', v: c }); i++
  }
  return toks
}

export function formatFormula(src, funcNames = []) {
  const names = new Set(funcNames.map(n => n.toUpperCase()))
  const toks = lex(src || '')
  // 函数名 / TRUE FALSE 大写
  toks.forEach((t, i) => {
    if (t.k !== 'id') return
    const nx = toks[i + 1]
    if ((nx?.k === '(' && names.has(t.v.toUpperCase())) || ['TRUE', 'FALSE'].includes(t.v.toUpperCase())) t.v = t.v.toUpperCase()
  })
  // 平铺版
  const flat = (from, to) => {
    let out = ''
    for (let i = from; i < to; i++) {
      const t = toks[i]
      const prev = toks[i - 1]
      if (t.k === 'op') {
        const unary = t.v === '-' && (!prev || prev.k === 'op' || prev.k === '(' || prev.k === ',')
        out += unary ? '-' : ` ${t.v} `
      } else if (t.k === ',') out += ', '
      else out += t.v
    }
    return out
  }
  const whole = flat(0, toks.length)
  if (whole.length <= 60) return whole
  // 长公式：最外层调用的参数逐行缩进（递归处理嵌套调用）
  const render = (from, to, depth) => {
    const text = flat(from, to)
    if (text.length <= 60 - depth * 2) return text
    // 找 from..to 内第一个顶层调用  ID ( ... )
    for (let i = from; i < to - 1; i++) {
      if (toks[i].k === 'id' && toks[i + 1].k === '(') {
        let d = 0
        let close = -1
        const commas = []
        for (let j = i + 1; j < to; j++) {
          if (toks[j].k === '(') d++
          else if (toks[j].k === ')') { d--; if (d === 0) { close = j; break } }
          else if (toks[j].k === ',' && d === 1) commas.push(j)
        }
        if (close < 0) return text
        const pad = '  '.repeat(depth + 1)
        const bounds = [i + 1, ...commas, close]
        const args = []
        for (let k = 0; k < bounds.length - 1; k++) args.push(render(bounds[k] + 1, bounds[k + 1], depth + 1))
        return `${flat(from, i)}${toks[i].v}(\n${args.map(a => pad + a).join(',\n')}\n${'  '.repeat(depth)})${flat(close + 1, to)}`
      }
    }
    return text
  }
  return render(0, toks.length, 0)
}

// ---------- 光标所在函数（签名提示）：返回 {name, argIndex} ----------
export function callContext(textBeforeCaret) {
  const s = textBeforeCaret || ''
  let depth = 0
  let argIndex = 0
  let quote = null
  // 先剔除字符串内容（反向扫描需要），简单做法：正向标记字符串区间
  const masked = []
  for (const c of s) {
    if (quote) { masked.push(' '); if (c === quote) quote = null; continue }
    if (c === '"' || c === "'") { quote = c; masked.push(' '); continue }
    masked.push(c)
  }
  for (let i = masked.length - 1; i >= 0; i--) {
    const c = masked[i]
    if (c === ')') depth++
    else if (c === '(') {
      if (depth === 0) {
        let j = i - 1
        while (j >= 0 && masked[j] === ' ') j--
        let k = j
        while (k >= 0 && isIdChar(masked[k])) k--
        const name = masked.slice(k + 1, j + 1).join('')
        if (!name) return null
        // 链式调用 值.FUNC( ：第一个参数是点前的值，括号内从第 2 个参数算起
        const chained = masked[k] === '.'
        return { name: name.toUpperCase(), argIndex: chained ? argIndex + 1 : argIndex, chained }
      }
      depth--
    } else if (c === ',' && depth === 0) argIndex++
  }
  return null
}

// 签名 "IF(a, b, [c])" → {head:'IF(', args:['a','b','[c]'], tail:')'}；链式写法「值1.COUNTA([值2, ...])」头部带 值1.
export function splitSignature(sig) {
  const open = sig.indexOf('(')
  const close = sig.lastIndexOf(')')
  if (open < 0 || close < open) return { head: sig, args: [], tail: '' }
  const inner = sig.slice(open + 1, close)
  const args = []
  let depth = 0
  let cur = ''
  for (const c of inner) {
    if (c === '[' || c === '(') depth++
    if (c === ']' || c === ')') depth--
    if (c === ',' && depth === 0) { args.push(cur.trim()); cur = ''; continue }
    cur += c
  }
  if (cur.trim()) args.push(cur.trim())
  const head = sig.slice(0, open + 1)
  const chainedPrefix = head.includes('.') ? head.slice(0, head.indexOf('.')) : null
  return { head, args, tail: sig.slice(close), chainedPrefix }
}
