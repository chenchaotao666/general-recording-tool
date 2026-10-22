// Smallest horizontal scroll that exposes a column between frozen regions.
export function fieldScrollLeft(columns, fieldName, scrollLeft, viewportWidth) {
  const target = columns.find(column => column.field === fieldName)
  if (!target || target.fixed || viewportWidth <= 0) return scrollLeft
  const width = column => Number(column.renderWidth) || 0
  const leftFrozen = columns.filter(c => c.fixed === 'left').reduce((n, c) => n + width(c), 0)
  const rightFrozen = columns.filter(c => c.fixed === 'right').reduce((n, c) => n + width(c), 0)
  const left = columns.slice(0, columns.indexOf(target)).reduce((n, c) => n + width(c), 0)
  const right = left + width(target)
  const start = scrollLeft + leftFrozen, end = scrollLeft + viewportWidth - rightFrozen
  if (end <= start || (left <= start && right >= end)) return scrollLeft
  if (left < start) return Math.max(0, left - leftFrozen)
  if (right > end) return Math.max(0, right - viewportWidth + rightFrozen)
  return scrollLeft
}

export function rowScrollTop(rowIndex, rowHeight, scrollTop, viewportHeight) {
  if (rowIndex < 0 || rowHeight <= 0 || viewportHeight <= 0) return scrollTop
  const top = rowIndex * rowHeight, bottom = top + rowHeight
  if (top <= scrollTop && bottom >= scrollTop + viewportHeight) return scrollTop
  if (top < scrollTop) return top
  if (bottom > scrollTop + viewportHeight) return Math.max(0, bottom - viewportHeight)
  return scrollTop
}
