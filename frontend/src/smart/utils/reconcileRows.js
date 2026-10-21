// API records are JSON values. Compare content, not property insertion order.
export function sameRecordValue(a, b) {
  if (Object.is(a, b)) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false
  if (Array.isArray(a) !== Array.isArray(b)) return false
  const keys = Object.keys(a)
  if (keys.length !== Object.keys(b).length) return false
  return keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && sameRecordValue(a[key], b[key]))
}

const recordKey = row => row.__rowType ? `${row.__rowType}:${row.key}` : row.id
export function reconcileRows(previous, incoming, keyOf = recordKey) {
  const byKey = new Map(previous.map(row => [keyOf(row), row]))
  let unchanged = previous.length === incoming.length
  const result = incoming.map((row, index) => {
    const key = keyOf(row)
    const old = key == null ? undefined : byKey.get(key)
    const next = old && sameRecordValue(old, row) ? old : row
    if (next !== previous[index]) unchanged = false
    return next
  })
  return unchanged ? previous : result
}
