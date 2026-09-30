// 表单公式求值器：与后端 services/expr.py 语义对齐的前端子集
// 支持：四则运算 / 比较 / and·or·not / 括号 / 数字·字符串·布尔常量；
// 函数：iff(cond,a,b) coalesce ifnull concat abs round floor ceil min max；
// 字段引用：标识符（qty * price）或 [任意字段名]。
// null 传播：任一侧为 null 运算结果为 null；除零 → null。

const FUNCS = {
  iff: 3, coalesce: null, ifnull: 2, concat: null,
  abs: 1, round: null, floor: 1, ceil: 1, min: null, max: null,
}

function tokenize(src) {
  const tokens = []
  let i = 0
  while (i < src.length) {
    const ch = src[i]
    if (/\s/.test(ch)) { i++; continue }
    if (ch === '[') {   // [任意字段名] 引用
      const j = src.indexOf(']', i)
      if (j < 0) throw new Error('括号引用未闭合')
      tokens.push({ t: 'field', v: src.slice(i + 1, j).trim() })
      i = j + 1
      continue
    }
    const mNum = src.slice(i).match(/^\d+(\.\d+)?/)
    if (mNum) { tokens.push({ t: 'num', v: parseFloat(mNum[0]) }); i += mNum[0].length; continue }
    const mStr = src.slice(i).match(/^(['"])((?:\\.|(?!\1).)*)\1/)
    if (mStr) { tokens.push({ t: 'str', v: mStr[2] }); i += mStr[0].length; continue }
    const mOp = src.slice(i).match(/^(==|!=|<=|>=|&&|\|\|)/)
    if (mOp) { tokens.push({ t: 'op', v: mOp[0] }); i += mOp[0].length; continue }
    if ('+-*/()<>,'.includes(ch)) { tokens.push({ t: 'op', v: ch }); i++; continue }
    const mId = src.slice(i).match(/^[A-Za-z_一-龥][A-Za-z0-9_一-龥]*/)
    if (mId) { tokens.push({ t: 'ident', v: mId[0] }); i += mId[0].length; continue }
    throw new Error(`无法识别的字符：${ch}`)
  }
  return tokens
}

class Parser {
  constructor(tokens, ctx) { this.tokens = tokens; this.pos = 0; this.ctx = ctx }
  peek() { return this.tokens[this.pos] }
  eat(v) {
    const t = this.tokens[this.pos]
    if (!t || (v !== undefined && t.v !== v)) throw new Error(`语法错误：期望 ${v}`)
    this.pos++
    return t
  }
  parse() { const v = this.orExpr(); if (this.pos < this.tokens.length) throw new Error('表达式末尾有多余内容'); return v }
  orExpr() {
    let l = this.andExpr()
    while (this.peek()?.v === 'or' || this.peek()?.v === '||') { this.pos++; const r = this.andExpr(); l = truth(l) || truth(r) }
    return l
  }
  andExpr() {
    let l = this.cmpExpr()
    while (this.peek()?.v === 'and' || this.peek()?.v === '&&') { this.pos++; const r = this.cmpExpr(); l = truth(l) && truth(r) }
    return l
  }
  cmpExpr() {
    let l = this.addExpr()
    const t = this.peek()
    if (t && ['==', '!=', '<', '<=', '>', '>='].includes(t.v)) {
      this.pos++
      const r = this.addExpr()
      if (l === null || r === null) return null
      switch (t.v) {
        case '==': return l === r
        case '!=': return l !== r
        case '<': return l < r
        case '<=': return l <= r
        case '>': return l > r
        default: return l >= r
      }
    }
    return l
  }
  addExpr() {
    let l = this.mulExpr()
    while (this.peek()?.v === '+' || this.peek()?.v === '-') {
      const op = this.eat().v
      const r = this.mulExpr()
      l = (l === null || r === null) ? null : (op === '+' ? num(l) + num(r) : num(l) - num(r))
    }
    return l
  }
  mulExpr() {
    let l = this.unary()
    while (this.peek()?.v === '*' || this.peek()?.v === '/') {
      const op = this.eat().v
      const r = this.unary()
      if (l === null || r === null) { l = null; continue }
      if (op === '/') { l = num(r) === 0 ? null : num(l) / num(r); continue }
      l = num(l) * num(r)
    }
    return l
  }
  unary() {
    const t = this.peek()
    if (t?.v === '-') { this.pos++; const v = this.unary(); return v === null ? null : -num(v) }
    if (t?.v === 'not' || t?.v === '!') { this.pos++; return !truth(this.unary()) }
    return this.primary()
  }
  primary() {
    const t = this.peek()
    if (!t) throw new Error('表达式意外结束')
    if (t.t === 'num') { this.pos++; return t.v }
    if (t.t === 'str') { this.pos++; return t.v }
    if (t.t === 'field') { this.pos++; return this.ctx[t.v] ?? null }
    if (t.t === 'ident') {
      this.pos++
      const name = t.v
      if (name === 'true') return true
      if (name === 'false') return false
      if (name === 'null') return null
      if (this.peek()?.v === '(') {   // 函数调用
        if (!(name in FUNCS)) throw new Error(`不支持的函数：${name}`)
        this.pos++
        const args = []
        if (this.peek()?.v !== ')') {
          args.push(this.orExpr())
          while (this.peek()?.v === ',') { this.pos++; args.push(this.orExpr()) }
        }
        this.eat(')')
        return callFunc(name, args)
      }
      return this.ctx[name] ?? null   // 字段引用
    }
    if (t.v === '(') { this.pos++; const v = this.orExpr(); this.eat(')'); return v }
    throw new Error(`语法错误：意外的 ${t.v ?? t.t}`)
  }
}

function truth(v) { return !!v }
function num(v) { return typeof v === 'number' ? v : parseFloat(v) || 0 }

function callFunc(name, args) {
  switch (name) {
    case 'iff': return truth(args[0]) ? args[1] : args[2]
    case 'coalesce': case 'ifnull': return args.find((a) => a !== null && a !== undefined) ?? null
    case 'concat': return args.some((a) => a === null || a === undefined) ? null : args.map(String).join('')
    case 'abs': return args[0] === null ? null : Math.abs(num(args[0]))
    case 'round': return args[0] === null ? null : roundTo(num(args[0]), args[1] === undefined ? 0 : Math.trunc(num(args[1])))
    case 'floor': return args[0] === null ? null : Math.floor(num(args[0]))
    case 'ceil': return args[0] === null ? null : Math.ceil(num(args[0]))
    case 'min': return args.some((a) => a === null) ? null : Math.min(...args.map(num))
    case 'max': return args.some((a) => a === null) ? null : Math.max(...args.map(num))
    default: return null
  }
}

// 四舍五入（对齐后端 round 的位数语义；浮点误差用 EPSILON 兜底）
function roundTo(v, n) {
  const p = 10 ** n
  return Math.round((v + Number.EPSILON) * p) / p
}

/**
 * 求值公式表达式。返回 null 表示无法计算（含配置错误），调用方按空值处理。
 * @param {string} src 表达式，如 "qty * price"、"round(amount * 0.13, 2)"
 * @param {object} ctx 字段值上下文 {字段名: 值}
 */
export function evalFormula(src, ctx) {
  if (!src || typeof src !== 'string') return null
  try {
    return new Parser(tokenize(src.trim()), ctx || {}).parse()
  } catch {
    return null
  }
}
