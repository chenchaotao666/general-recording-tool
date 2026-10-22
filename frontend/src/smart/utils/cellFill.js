import { planPaste } from './cellClipboard.js'

const numericTypes = new Set(['number', 'currency', 'percent', 'progress'])

function decimalPlaces(value) {
  const [mantissa, exponent = '0'] = String(value).toLowerCase().split('e')
  return Math.max(0, (mantissa.split('.')[1]?.length || 0) - Number(exponent))
}

function numericSeries(matrix, column, field) {
  if (matrix.length < 2) return null
  const cells = matrix.map(row => row[column])
  if (!cells.every(cell => numericTypes.has(cell?.type) && typeof cell.value === 'number' && Number.isFinite(cell.value))) return null
  // Excel's default numeric fill extends a linear trend; an arithmetic series
  // is the common case. Fit relative to the first value to reduce cancellation.
  const first = cells[0].value, n = cells.length, middle = (n - 1) / 2
  const mean = cells.reduce((sum, cell) => sum + (cell.value - first), 0) / n
  let numerator = 0, denominator = 0
  cells.forEach((cell, i) => {
    numerator += (i - middle) * (cell.value - first - mean)
    denominator += (i - middle) ** 2
  })
  const step = numerator / denominator
  const configured = field?.options?.precision
  const precision = configured != null && configured !== 'default'
    ? Number(configured) : Math.max(2, ...cells.map(cell => decimalPlaces(cell.value)))
  const digits = Math.min(15, Math.max(0, Number.isFinite(precision) ? precision : 2))
  return index => Number(Number((first + mean + (index - middle) * step).toPrecision(15)).toFixed(digits))
}

// Numeric columns extend independently; other columns repeat their pattern.
export function planFill(matrix, rows, fields, source, targetRow, canEdit) {
  const changes = [], skipped = []
  const series = matrix[0].map((_, column) => numericSeries(matrix, column, fields[source.left + column]))
  const start = targetRow < source.top ? targetRow : source.bottom + 1
  const stop = targetRow < source.top ? source.top - 1 : targetRow
  for (let r = start; r <= stop; r++) {
    const index = ((r - source.top) % matrix.length + matrix.length) % matrix.length
    const cells = matrix[index].map((cell, column) => {
      if (!series[column]) return cell
      const value = series[column](r - source.top)
      return { ...cell, value, text: String(value) }
    })
    const plan = planPaste([cells], rows, fields,
      { top: r, bottom: r, left: source.left, right: source.right }, canEdit)
    changes.push(...plan.changes)
    skipped.push(...plan.skipped)
  }
  return { changes, skipped }
}
