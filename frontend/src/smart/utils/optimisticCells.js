import { cellType } from './cellClipboard.js'
import { mergeUpdatedRows, sameRecordValue } from './reconcileRows.js'

export function previewCells(rows, changes) {
  const byId = new Map(rows.filter(row => !row.__rowType).map(row => [row.id, row]))
  const updates = new Map(), snapshots = []
  for (const { row, field, value, labels } of changes) {
    const current = byId.get(row.id)
    if (!current) continue
    let next = value
    if (labels) {
      const ids = labels.map(label => field.options?.options?.find(option => option.label === label)?.id)
      // New options need server-assigned IDs; existing options can render immediately.
      if (ids.some(id => id == null)) continue
      next = cellType(field) === 'singleSelect' ? ids[0] ?? null : ids
    }
    snapshots.push({ id: row.id, field: field.field_name, before: current[field.field_name], next })
    const update = updates.get(row.id) || { id: row.id }
    update[field.field_name] = next
    updates.set(row.id, update)
  }
  return { rows: mergeUpdatedRows(rows, [...updates.values()]), snapshots }
}

export function rollbackCells(rows, snapshots, accepted = new Set()) {
  const byId = new Map(rows.filter(row => !row.__rowType).map(row => [row.id, row]))
  const updates = new Map()
  for (const cell of snapshots) {
    const current = byId.get(cell.id)
    if (!current || accepted.has(`${cell.id}:${cell.field}`) || !sameRecordValue(current[cell.field], cell.next)) continue
    const update = updates.get(cell.id) || { id: cell.id }
    update[cell.field] = cell.before
    updates.set(cell.id, update)
  }
  return mergeUpdatedRows(rows, [...updates.values()])
}
