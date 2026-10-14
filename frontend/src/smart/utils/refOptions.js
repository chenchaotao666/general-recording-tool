// 引用选项与选项联动（设计文档 §3.3）：纯函数，便于单测
// - reference 模式：选项集来自他表 select 字段，源表变更自动同步
// - 选项联动：本表行字段值 vs 引用表行字段值（一期仅 eq），命中行的引用字段值才是可选项

// 字段的可用选项集：reference 模式取引用字段的选项，否则取本地 options
export function resolveRefOptions(field, refField) {
  const cfg = field?.options || {}
  if (cfg.optionSource !== 'reference') return cfg.options || []
  return refField?.options?.options || []
}

// 标量/数组混比：optionId 与数字等按字符串对齐；本表字段值为空 → 不匹配
function eqVal(local, remote) {
  if (local == null || local === '' || (Array.isArray(local) && !local.length)) return false
  if (Array.isArray(local) || Array.isArray(remote)) {
    const ls = new Set((Array.isArray(local) ? local : [local]).map(String))
    return (Array.isArray(remote) ? remote : [remote]).some(x => ls.has(String(x)))
  }
  return String(local) === String(remote)
}

// 选项联动过滤：满足条件的引用表行，其引用字段的值组成可选项集合
// linkage: {enabled, match: 'all'|'any', conditions: [{localFieldId, operator, remoteFieldId}]}
export function filterLinkageOptions(options, linkage, record, remoteRows, refFieldId) {
  if (!linkage?.enabled) return options || []
  const conds = (linkage.conditions || []).filter(c => c.localFieldId && c.remoteFieldId)
  if (!conds.length) return options || []
  const match = linkage.match === 'any' ? 'any' : 'all'
  const available = new Set()
  for (const row of remoteRows || []) {
    const hits = conds.map(c => eqVal(record?.[c.localFieldId], row[c.remoteFieldId]))
    if (match === 'all' ? hits.every(Boolean) : hits.some(Boolean)) {
      const v = row[refFieldId]
      for (const id of Array.isArray(v) ? v : [v]) {
        if (id != null && id !== '') available.add(id)
      }
    }
  }
  return (options || []).filter(o => available.has(o.id))
}
