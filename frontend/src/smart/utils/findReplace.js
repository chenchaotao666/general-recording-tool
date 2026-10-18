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
