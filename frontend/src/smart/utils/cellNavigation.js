export function nextCell(rows, fields, current, direction) {
  if (!current) return null
  const records = rows.filter(row => !row.__rowType)
  const rowIndex = records.findIndex(row => row.__key === current.key)
  const columnIndex = fields.findIndex(field => field.field_name === current.fieldName)
  if (rowIndex < 0 || columnIndex < 0) return null
  const rowStep = direction === 'down' ? 1 : direction === 'up' ? -1 : 0
  const columnStep = direction === 'right' ? 1 : direction === 'left' ? -1 : 0
  const row = records[Math.max(0, Math.min(records.length - 1, rowIndex + rowStep))]
  const field = fields[Math.max(0, Math.min(fields.length - 1, columnIndex + columnStep))]
  return { key: row.__key, fieldName: field.field_name }
}
