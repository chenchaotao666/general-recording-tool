// Insert server-created records without replacing existing row objects or moving selection.
export function insertViewRows(rows, records, anchorId, direction, pageSize = Infinity) {
  if (!records.length) return null
  if (anchorId == null) return [...records, ...rows].slice(0, pageSize)
  const index = rows.findIndex(row => row.id === anchorId && !row.__rowType)
  if (index < 0) return null
  let offset = index
  if (direction === 'down') {
    offset++
    const descendants = new Set([anchorId])
    while (offset < rows.length && descendants.has(rows[offset].parent_id)) {
      descendants.add(rows[offset].id)
      offset++
    }
  }
  return [...rows.slice(0, offset), ...records, ...rows.slice(offset)].slice(0, pageSize)
}

export function canInsertLocally(config, grouped, managed, viewType) {
  return managed && viewType === 'grid' && !grouped && !(config.groups || []).length
    && !(config.sorts || []).length && !(config.filters?.conditions || []).length
}
