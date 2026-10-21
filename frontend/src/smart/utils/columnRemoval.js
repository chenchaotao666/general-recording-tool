function isSubsequence(before, after) {
  let index = 0
  return after.every(value => {
    while (index < before.length && before[index] !== value) index++
    return index++ < before.length
  })
}

// Removing columns preserves the registration order of every surviving column.
export function isColumnRemoval(before, after) {
  if (!isSubsequence(before.map(node => node[0]), after.map(node => node[0]))) return false
  const previous = new Map(before.map(node => [node[0], node]))
  return after.every(([key, fixed, fields]) => {
    const old = previous.get(key)
    if (!old || old[1] !== fixed || Array.isArray(old[2]) !== Array.isArray(fields)) return false
    return Array.isArray(fields) ? isSubsequence(old[2], fields) : old[2] === fields
  })
}

// VXE inserts newly mounted columns at their DOM index. Existing registrations
// can survive additions as long as their order, group and frozen side stay put.
export function isColumnInsertion(before, after) {
  return isColumnRemoval(after, before)
}
