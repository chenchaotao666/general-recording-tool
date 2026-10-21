// 「添加一行」的初始值：按当前视图的筛选条件推导，让新记录能命中筛选、出现在表格里。
// 规则（与后端 smart_cond / pyquery 同口径，用 matchCondition 校验）：
//   AND（全部条件）：按字段归并，每个字段从各条件推导的候选值中取第一个能同时满足该字段全部条件的值；
//   OR（任一条件）：新记录本身已能命中某条件（如「为空」）则不预设；否则取第一个能推导出值的条件。
// 只读/系统字段（公式、查找引用、自动编号、创建人等）无法预设，跳过；推导不出时尽力而为（不保证可见）。
import { regOf } from '../registry/fieldRegistry.js'
import { dateModeRange, isDateModeValue, matchCondition } from './format.js'

const VIEWER = '$viewer'
const SKIP = Symbol('skip')   // 该条件无法通过预设满足
const EMPTY = Symbol('empty') // 新记录保持为空即可满足
const NUMBER_TYPES = ['number', 'percent', 'currency', 'progress']
const DATE_TYPES = ['date']
const TEXT_TYPES = ['text']
const PLACEHOLDER = '新记录'

const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const shiftDay = (s, n) => { const d = new Date(`${s}T00:00:00`); d.setDate(d.getDate() + n); return ymd(d) }
const asDateTime = (s) => `${s} 00:00:00`   // 与日期单元格编辑器 value-format 一致
const toList = (v) => (Array.isArray(v) ? v : v == null || v === '' ? [] : [v])
const toBool = (v) => v === true || ['true', '1', '是'].includes(String(v).toLowerCase())

// 枚举类字段（单选/多选/人员/关联）的可选 id 池：用于「不等于 / 不包含」挑一个条件之外的值
function poolOf(f, ctx) {
  const ft = f.field_type
  if (ft === 'singleSelect' || ft === 'multiSelect') return (f.options?.options || []).map(o => o.id)
  if (ft === 'member') return (ctx.members || []).map(m => m.id)
  if (ft === 'relation') return (ctx.relationRows?.get(f.options?.targetTableId) || []).map(r => r.id)
  return []
}
// 值是否存数组：多选恒为数组；人员/关联按字段的「允许多个」设置（默认多个）
function isMultiValued(f) {
  if (f.field_type === 'multiSelect') return true
  if (f.field_type === 'member' || f.field_type === 'relation') return f.options?.multiple !== false
  return false
}

function nonEmptyValue(f, ctx, today) {
  const ft = f.field_type
  if (NUMBER_TYPES.includes(ft)) return 0
  if (DATE_TYPES.includes(ft)) return asDateTime(today)
  if (ft === 'checkbox') return true
  if (TEXT_TYPES.includes(ft)) return PLACEHOLDER
  const first = (ft === 'member' && ctx.viewerId != null) ? ctx.viewerId : poolOf(f, ctx)[0]
  if (first == null) return SKIP
  return isMultiValued(f) ? [first] : first
}

// 单个条件 → 候选值（SKIP = 推导不出；EMPTY = 保持为空）
function candidateFor(c, f, ctx, today) {
  const ft = f.field_type
  const op = c.operator
  const v = c.value
  if (op === 'isEmpty') return EMPTY
  if (op === 'isNotEmpty') return nonEmptyValue(f, ctx, today)

  if (NUMBER_TYPES.includes(ft)) {
    const n = Number(v)
    if (v == null || v === '' || Number.isNaN(n)) return SKIP
    return { eq: n, gte: n, lte: n, gt: n + 1, lt: n - 1, neq: n + 1 }[op] ?? SKIP
  }

  if (DATE_TYPES.includes(ft)) {
    if (['today', 'pastDays', 'withinDays'].includes(op)) return asDateTime(today)
    const rng = isDateModeValue(v) ? dateModeRange(v)
      : (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v) ? [v.slice(0, 10), v.slice(0, 10)] : null)
    if (!rng) return SKIP
    const [lo, hi] = rng
    const d = { eq: lo, gte: lo, lte: hi, gt: shiftDay(hi, 1), lt: shiftDay(lo, -1), neq: shiftDay(hi, 1) }[op]
    return d ? asDateTime(d) : SKIP
  }

  if (ft === 'checkbox') {
    if (op === 'eq') return toBool(v)
    if (op === 'neq') return !toBool(v)
    return SKIP
  }

  if (['singleSelect', 'multiSelect', 'member', 'relation'].includes(ft)) {
    const want = toList(v)
    let picked
    if (op === 'eq' && ft === 'member' && want.length) return isMultiValued(f) ? want : want[0]   // 人员「等于」= 集合完全相同
    if (op === 'eq' || op === 'contains') picked = want[0]
    else if (op === 'neq' || op === 'notContains') picked = poolOf(f, ctx).find(id => !want.map(String).includes(String(id)))
    if (picked == null) return SKIP
    return isMultiValued(f) ? [picked] : picked
  }

  if (TEXT_TYPES.includes(ft)) {
    const s = v == null ? '' : String(v)
    if ((op === 'eq' || op === 'contains') && s) return s
    if (op === 'neq' || op === 'notContains') {
      const bad = (x) => (op === 'neq' ? x === s : s && x.toLowerCase().includes(s.toLowerCase()))
      return [PLACEHOLDER, `${PLACEHOLDER}1`, '-'].find(x => !bad(x)) ?? SKIP
    }
  }
  return SKIP
}

// 条件里的「我」替换为当前用户 id，便于本地校验与写入
function resolveViewer(c, viewerId) {
  const sub = (x) => (x === VIEWER ? viewerId : x)
  const value = Array.isArray(c.value) ? c.value.filter(x => x !== VIEWER || viewerId != null).map(sub) : sub(c.value)
  return { ...c, value }
}

const hits = (value, conds) => conds.every(c => matchCondition(c, value === EMPTY ? null : value))

/**
 * @param {object} p
 * @param {Array} p.conditions  视图生效的筛选条件（{fieldId, operator, value}）
 * @param {string} p.conjunction 'and' | 'or'
 * @param {Array} p.fields      字段元数据
 * @param {*} p.viewerId        当前用户 id（「我」）
 * @param {Array} p.members     成员 [{id, name}]
 * @param {Map} p.relationRows  关联目标表 id → [{id, label}]
 * @returns {object} 新记录 data 预设
 */
export function presetFromFilters({ conditions = [], conjunction = 'and', fields = [], viewerId = null,
  members = [], relationRows = new Map(), now = new Date() } = {}) {
  const ctx = { viewerId, members, relationRows }
  const today = ymd(now)
  const byName = new Map(fields.map(f => [f.field_name, f]))
  const editable = (f) => f && !regOf(f).readonly && !regOf(f).system
  const conds = conditions.filter(c => c?.fieldId && c.operator && byName.has(c.fieldId)).map(c => resolveViewer(c, viewerId))
  if (!conds.length) return {}

  if (conjunction === 'or') {
    // 新记录天然命中的条件（可编辑字段为空 / 创建人含我）→ 无需预设
    const naturally = conds.some(c => {
      const f = byName.get(c.fieldId)
      if (editable(f)) return c.operator === 'isEmpty'
      return f.field_type === 'createdBy' && viewerId != null && toList(c.value).map(String).includes(String(viewerId))
    })
    if (naturally) return {}
    for (const c of conds) {
      const f = byName.get(c.fieldId)
      if (!editable(f)) continue
      const v = candidateFor(c, f, ctx, today)
      if (v !== SKIP && v !== EMPTY && hits(v, [c])) return { [c.fieldId]: v }
    }
    return {}
  }

  // AND：逐字段求同时满足该字段全部条件的值
  const preset = {}
  const grouped = new Map()
  for (const c of conds) grouped.set(c.fieldId, [...(grouped.get(c.fieldId) || []), c])
  for (const [name, fieldConds] of grouped) {
    const f = byName.get(name)
    if (!editable(f)) continue
    const candidates = fieldConds.map(c => candidateFor(c, f, ctx, today)).filter(v => v !== SKIP)
    if (!fieldConds.some(c => c.operator === 'isEmpty')) candidates.push(EMPTY)   // 兜底：也试试保持为空
    const pick = candidates.find(v => hits(v, fieldConds))
      ?? candidates.find(v => v !== EMPTY)   // 无解（条件互斥）时尽力而为
    if (pick !== undefined && pick !== EMPTY) preset[name] = pick
  }
  return preset
}
