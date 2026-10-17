// 表单显示条件求值（与后端 smart_cond.match_conditions 同语义，提交时服务端复核）

const isEmpty = (v) => v == null || v === '' || (Array.isArray(v) && !v.length)

function asList(v) { return Array.isArray(v) ? v.map(String) : (isEmpty(v) ? [] : [String(v)]) }

export function matchCond(c, data) {
  const v = data[c.fieldId]
  const want = c.value
  switch (c.operator) {
    case 'isEmpty': return isEmpty(v)
    case 'isNotEmpty': return !isEmpty(v)
    case 'eq':
      if (Array.isArray(want)) return asList(want).length === 1 && asList(v).includes(asList(want)[0])
      return String(v ?? '') === String(want ?? '')
    case 'neq':
      if (Array.isArray(want)) return !(asList(want).length === 1 && asList(v).includes(asList(want)[0]))
      return String(v ?? '') !== String(want ?? '')
    case 'contains':
      if (Array.isArray(want) || Array.isArray(v)) return asList(want).some(x => asList(v).includes(x))
      return !isEmpty(v) && String(v).toLowerCase().includes(String(want ?? '').toLowerCase())
    case 'notContains':
      if (Array.isArray(want) || Array.isArray(v)) return !asList(want).some(x => asList(v).includes(x))
      return isEmpty(v) || !String(v).toLowerCase().includes(String(want ?? '').toLowerCase())
    case 'gt': return Number(v) > Number(want)
    case 'gte': return Number(v) >= Number(want)
    case 'lt': return Number(v) < Number(want)
    case 'lte': return Number(v) <= Number(want)
    default: return true
  }
}

export function isItemVisible(item, data) {
  const vis = item.visibility
  const conds = (vis?.conditions || []).filter(c => c.fieldId)
  if (!conds.length) return true
  return vis.match === 'any' ? conds.some(c => matchCond(c, data)) : conds.every(c => matchCond(c, data))
}

// 计算类字段在表单中的只读占位文案（§12.2）
export function readonlyHint(fieldType) {
  return {
    formula: '公式计算结果不可直接编辑',
    lookup: '查找引用内容不可直接编辑',
    autoNumber: '自动编号由系统生成',
    ai: 'AI 字段由 AI 自动生成',
  }[fieldType] || '该字段不可直接编辑'
}
