// 查找结果与网格单元格共用稳定 key，避免每个单元格重复扫描完整命中数组。
export function findCellKey(recordId, fieldName) {
  return `${recordId}::${fieldName}`
}

export function findMatchKeys(matches = []) {
  return new Set(matches.map(m => findCellKey(m.recordId, m.field)))
}

export function currentFindKey(matches = [], currentIndex = -1) {
  const match = matches[currentIndex]
  return match ? findCellKey(match.recordId, match.field) : ''
}

// Start at the current page, continue to the end, then wrap to the top.
export function orderFindMatches(matches = [], rows = [], fields = []) {
  const ranks = new Map()
  for (const row of rows) {
    if (row.__rowType) continue
    for (const field of fields) {
      const key = findCellKey(row.id, field.field_name)
      if (!ranks.has(key)) ranks.set(key, ranks.size)
    }
  }
  const rank = match => ranks.get(findCellKey(match.recordId, match.field)) ?? Infinity
  const current = matches.filter(m => rank(m) !== Infinity).sort((a, b) => rank(a) - rank(b))
  if (!current.length) return [...matches]
  const start = matches.indexOf(current[0])
  const remaining = [...matches.slice(start), ...matches.slice(0, start)]
    .filter(m => rank(m) === Infinity)
  return [...current, ...remaining]
}
