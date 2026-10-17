// 智能表格式化工具（纯函数，vitest 可测）

export function formatNumber(v, cfg = {}) {
  if (v == null || v === '') return ''
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  let s = cfg.precision != null && cfg.precision !== 'default' ? n.toFixed(cfg.precision) : String(v)
  if (cfg.thousandSeparator) {
    const [int, dec] = s.split('.')
    s = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (dec ? `.${dec}` : '')
  }
  return s
}

export function formatCurrency(v, cfg = {}) {
  if (v == null || v === '') return ''
  return `${cfg.currencySymbol || '￥'}${formatNumber(v, { precision: cfg.precision ?? 2, thousandSeparator: cfg.thousandSeparator !== false })}`
}

export function formatDate(v, cfg = {}) {
  if (!v) return ''
  const s = String(v)
  const fmt = cfg.format || 'yyyy-MM-dd'
  const d = new Date(s.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return s.slice(0, 10)
  const pad = (x) => String(x).padStart(2, '0')
  const map = {
    'yyyy-MM-dd': `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    'yyyy/MM/dd': `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`,
    'yyyy年M月d日': `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`,
    'yyyy-MM-dd HH:mm': `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`,
    'yyyy年M月d日 HH:mm': `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`,
  }
  return map[fmt] || s.slice(0, cfg.includeTime ? 16 : 10)
}

// 日期字段格式（yyyy… 写法）→ dayjs 格式，供日期编辑框 format/placeholder 使用，显示结果与 formatDate 一致
const DAYJS_DATE_FORMATS = {
  'yyyy-MM-dd': 'YYYY-MM-DD', 'yyyy/MM/dd': 'YYYY/M/D', 'yyyy年M月d日': 'YYYY年M月D日',
  'yyyy-MM-dd HH:mm': 'YYYY-MM-DD HH:mm', 'yyyy年M月d日 HH:mm': 'YYYY年M月D日 HH:mm',
}
export function dayjsDateFormat(cfg = {}) {
  return DAYJS_DATE_FORMATS[cfg.format || 'yyyy-MM-dd'] || (cfg.includeTime ? 'YYYY-MM-DD HH:mm' : 'YYYY-MM-DD')
}

// 填色规则求值（设计文档 §5.5）：返回命中的颜色或 null。
// 整列规则（fillTarget）：all=该列所有内容单元格恒命中（排最后，条件规则优先）；
// header=字段名称（表头）填色，不参与单元格求值（由 header-cell-style 应用）
export function evalFillRules(rules, field, value) {
  const hit = (rules || [])
    .filter(r => r.fieldId === field.field_name && r.color && r.fillTarget !== 'header' && isRuleComplete(r))
    .sort((a, b) => ((a.fillTarget === 'all') - (b.fillTarget === 'all')) || ((a.order ?? 0) - (b.order ?? 0)))
  for (const r of hit) {
    if (r.fillTarget === 'all') return r.color
    if (matchCondition(r, value)) return r.color
  }
  return null
}

// 字段名称（表头）填色：返回该字段 header 规则的底色或 null
export function headerFillColor(rules, fieldName) {
  const r = (rules || []).find(r => r.fieldId === fieldName && r.fillTarget === 'header' && r.color)
  return r ? r.color : null
}

// 整行填色求值：规则勾了 wholeRow 时，命中条件则整行所有单元格填色（优先级低于单元格自身的规则）
export function evalRowFill(rules, fields, row) {
  const hit = (rules || [])
    .filter(r => r.wholeRow && !r.fillTarget && r.color && isRuleComplete(r))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  for (const r of hit) {
    const f = fields.find(x => x.field_name === r.fieldId)
    if (f && matchCondition(r, row[f.field_name])) return r.color
  }
  return null
}

// ---------- 日期筛选值的「日期模式」（具体日期 / 今天 / 本周 / 过去 7 天内…，参照 PixPin_2026-10-18_00-16-20） ----------
// 条件值 = { mode, date? }：按当天换算闭区间 [lo, hi]（YYYY-MM-DD），再按运算符比较。后端 pyquery.date_mode_range 同口径
export const DATE_MODE_OPTIONS = [
  { value: 'exact', label: '具体日期' },
  { value: 'today', label: '今天' }, { value: 'tomorrow', label: '明天' }, { value: 'yesterday', label: '昨天' },
  { value: 'thisWeek', label: '本周' }, { value: 'lastWeek', label: '上周' },
  { value: 'thisMonth', label: '本月' }, { value: 'lastMonth', label: '上月' },
  { value: 'past7', label: '过去 7 天内' }, { value: 'next7', label: '未来 7 天内' },
  { value: 'past30', label: '过去 30 天内' }, { value: 'next30', label: '未来 30 天内' },
]
// 运算符可用的日期模式：等于/不等于 = 全部；晚于/早于 = 具体日期/今天/明天/昨天（参照 PixPin_2026-10-18_00-48-27）
const POINT_MODES = ['exact', 'today', 'tomorrow', 'yesterday']
export function dateModesFor(op) {
  return ['gt', 'lt', 'gte', 'lte'].includes(op) ? DATE_MODE_OPTIONS.filter(o => POINT_MODES.includes(o.value)) : DATE_MODE_OPTIONS
}
export const isDateModeValue = (v) => !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.mode === 'string'
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
export function dateModeRange(v, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const pair = (a, b) => [ymd(a), ymd(b)]
  switch (v?.mode) {
    case 'exact': return v.date ? [String(v.date).slice(0, 10), String(v.date).slice(0, 10)] : null
    case 'today': return pair(today, today)
    case 'tomorrow': return pair(addDays(today, 1), addDays(today, 1))
    case 'yesterday': return pair(addDays(today, -1), addDays(today, -1))
    case 'thisWeek': case 'lastWeek': {   // 周一 ~ 周日
      const mon = addDays(today, -((today.getDay() + 6) % 7) - (v.mode === 'lastWeek' ? 7 : 0))
      return pair(mon, addDays(mon, 6))
    }
    case 'thisMonth': return pair(new Date(today.getFullYear(), today.getMonth(), 1), new Date(today.getFullYear(), today.getMonth() + 1, 0))
    case 'lastMonth': return pair(new Date(today.getFullYear(), today.getMonth() - 1, 1), new Date(today.getFullYear(), today.getMonth(), 0))
    case 'past7': return pair(addDays(today, -6), today)
    case 'next7': return pair(today, addDays(today, 6))
    case 'past30': return pair(addDays(today, -29), today)
    case 'next30': return pair(today, addDays(today, 29))
    default: return null
  }
}
export function dateModeLabel(v) {
  if (!isDateModeValue(v)) return v == null ? '' : String(v)
  if (v.mode === 'exact') return v.date ? String(v.date).slice(0, 10) : ''
  return DATE_MODE_OPTIONS.find(o => o.value === v.mode)?.label || ''
}
// 条件值是否为空（未填完）：null/空串/空数组；日期模式「具体日期」未选日期也算空
export function isCondValueEmpty(v) {
  if (isDateModeValue(v)) return v.mode === 'exact' && !v.date
  return v == null || v === '' || (Array.isArray(v) && !v.length)
}

export function isRuleComplete(r) {
  // 整列规则（fillTarget header/all）无需运算符与取值即完整
  if (r.fillTarget) return !!r.fieldId
  const noValue = ['isEmpty', 'isNotEmpty']
  return r.fieldId && r.operator && (noValue.includes(r.operator) || !isCondValueEmpty(r.value))
}

export function matchCondition(c, v) {
  const empty = v == null || v === '' || (Array.isArray(v) && !v.length)
  // 任一侧为数组（枚举/人员的条件多选、或多选单元格值）：按集合交集判断（与后端 pyquery 一致），
  // 不能把条件数组 String() 成逗号串再做子串匹配——那样标量单元格永不命中
  const setHit = () => {
    const cell = new Set((Array.isArray(v) ? v : [v]).map(String))
    return (Array.isArray(c.value) ? c.value : [c.value]).map(String).some(x => cell.has(x))
  }
  // 日期比较：单元格值带时间部分（2026-10-08 00:00:00）、条件值可能只是日期——
  // 按条件值的精度截断单元格值后按 ISO 字典序比较（ISO 日期/日期时间字典序即时间序）
  const DATE_RE = /^\d{4}-\d{2}-\d{2}/
  // 日期模式值（今天/本周/具体日期…）：单元格日期落在换算区间的位置决定命中
  if (isDateModeValue(c.value) && ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'].includes(c.operator)) {
    const rng = dateModeRange(c.value)
    const m = String(v ?? '').match(DATE_RE)
    if (!rng || empty || !m) return false
    const d = m[0]
    const [lo, hi] = rng
    return { eq: d >= lo && d <= hi, neq: !(d >= lo && d <= hi), gt: d > hi, gte: d >= lo, lt: d < lo, lte: d <= hi }[c.operator]
  }
  const isDateCond = typeof c.value === 'string' && DATE_RE.test(c.value)
  const dateKey = (x) => String(x).slice(0, String(c.value).length)
  // 相对日期：今天 / 过去 N 天（含今天）/ 未来 N 天（含今天）
  const dayOf = (x) => { const m = String(x).match(DATE_RE); return m ? new Date(`${m[0]}T00:00:00`) : null }
  if (['today', 'pastDays', 'withinDays'].includes(c.operator)) {
    const dv = dayOf(v)
    if (!dv) return false
    const today = new Date(); today.setHours(0, 0, 0, 0)
    const diff = Math.round((dv - today) / 86400000)
    if (c.operator === 'today') return diff === 0
    const n = Number(c.value) || 1
    return c.operator === 'pastDays' ? diff <= 0 && diff >= -(n - 1) : diff >= 0 && diff <= n
  }
  switch (c.operator) {
    case 'isEmpty': return empty
    case 'isNotEmpty': return !empty
    case 'eq': return Array.isArray(c.value) ? setHit()
      : isDateCond ? !empty && DATE_RE.test(String(v)) && dateKey(v) === c.value
      : !empty && String(v) === String(c.value)
    case 'neq': return Array.isArray(c.value) ? !setHit()
      : isDateCond ? !empty && !(DATE_RE.test(String(v)) && dateKey(v) === c.value)
      : !empty && String(v) !== String(c.value)
    case 'contains':
      if (Array.isArray(v) || Array.isArray(c.value)) return setHit()
      return !empty && String(v).toLowerCase().includes(String(c.value).toLowerCase())
    case 'notContains':
      if (Array.isArray(v) || Array.isArray(c.value)) return !setHit()
      return !empty && !String(v).toLowerCase().includes(String(c.value).toLowerCase())
    case 'gt': return !empty && (isDateCond ? DATE_RE.test(String(v)) && dateKey(v) > c.value : Number(v) > Number(c.value))
    case 'gte': return !empty && (isDateCond ? DATE_RE.test(String(v)) && dateKey(v) >= c.value : Number(v) >= Number(c.value))
    case 'lt': return !empty && (isDateCond ? DATE_RE.test(String(v)) && dateKey(v) < c.value : Number(v) < Number(c.value))
    case 'lte': return !empty && (isDateCond ? DATE_RE.test(String(v)) && dateKey(v) <= c.value : Number(v) <= Number(c.value))
    default: return false
  }
}

// 撤销/重做命令栈（记录级，设计文档 §7.6）
export function createUndoStack(limit = 50) {
  const undoStack = []
  const redoStack = []
  return {
    push(cmd) {   // cmd: {label, undo, redo}
      undoStack.push(cmd)
      if (undoStack.length > limit) undoStack.shift()
      redoStack.length = 0
    },
    async undo() {
      const cmd = undoStack.pop()
      if (!cmd) return null
      await cmd.undo()
      redoStack.push(cmd)
      return cmd
    },
    async redo() {
      const cmd = redoStack.pop()
      if (!cmd) return null
      await cmd.redo()
      undoStack.push(cmd)
      return cmd
    },
    clear() { undoStack.length = 0; redoStack.length = 0 },
    get canUndo() { return undoStack.length > 0 },
    get canRedo() { return redoStack.length > 0 },
  }
}
