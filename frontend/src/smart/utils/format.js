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

// 填色规则求值（设计文档 §5.5）：返回命中的颜色或 null
export function evalFillRules(rules, field, value) {
  const hit = (rules || [])
    .filter(r => r.fieldId === field.field_name && r.color && isRuleComplete(r))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  for (const r of hit) {
    if (matchCondition(r, value)) return r.color
  }
  return null
}

export function isRuleComplete(r) {
  const noValue = ['isEmpty', 'isNotEmpty']
  return r.fieldId && r.operator && (noValue.includes(r.operator) || (r.value != null && r.value !== ''))
}

export function matchCondition(c, v) {
  const empty = v == null || v === '' || (Array.isArray(v) && !v.length)
  switch (c.operator) {
    case 'isEmpty': return empty
    case 'isNotEmpty': return !empty
    case 'eq': return !empty && String(v) === String(c.value)
    case 'neq': return !empty && String(v) !== String(c.value)
    case 'contains':
      if (Array.isArray(v)) {
        const want = Array.isArray(c.value) ? c.value.map(String) : [String(c.value)]
        return v.map(String).some(x => want.includes(x))
      }
      return !empty && String(v).toLowerCase().includes(String(c.value).toLowerCase())
    case 'notContains':
      if (Array.isArray(v)) {
        const want = Array.isArray(c.value) ? c.value.map(String) : [String(c.value)]
        return !v.map(String).some(x => want.includes(x))
      }
      return !empty && !String(v).toLowerCase().includes(String(c.value).toLowerCase())
    case 'gt': return !empty && Number(v) > Number(c.value)
    case 'gte': return !empty && Number(v) >= Number(c.value)
    case 'lt': return !empty && Number(v) < Number(c.value)
    case 'lte': return !empty && Number(v) <= Number(c.value)
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
