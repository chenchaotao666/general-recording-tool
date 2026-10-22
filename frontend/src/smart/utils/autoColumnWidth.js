export function rowHeightPixels(value) {
  if (typeof value === 'number') return Math.max(36, 14 + 22 * value)
  return { default: 36, medium: 52, tall: 76, extraTall: 100 }[value] || 36
}

export function tagRowCapacity(height) {
  return Math.max(1, Math.floor((Math.max(24, height - 12) + 4) / 28))
}

function smallestWidth(fits, maximum) {
  let low = 1, high = maximum
  while (low < high) {
    const mid = Math.floor((low + high) / 2)
    if (fits(mid)) high = mid
    else low = mid + 1
  }
  return low
}

// Match the grid's word-break: break-all, normal whitespace and 22px text lines.
export function wrappedTextWidth(text, height, measure, maximum = 276) {
  text = String(text ?? '').replace(/\s+/g, ' ')
  if (!text) return 0
  const lines = height <= 36 ? 1 : Math.max(1, Math.floor((height - 8) / 22))
  if (lines === 1) return Math.min(maximum, measure(text))
  const widths = Array.from(text, char => measure(char))
  return smallestWidth(width => {
    let rows = 1, used = 0
    for (const size of widths) {
      if (size > width) return false
      if (used + size > width) { rows++; used = 0 }
      if (rows > lines) return false
      used += size
    }
    return true
  }, maximum)
}

// Keep complete labels where possible; widening cannot reduce the number of fitted rows.
export function wrappedTagWidth(widths, height, { stacked = false, badgeWidth = 28, maximum = 276 } = {}) {
  if (!widths.length) return 0
  const rows = tagRowCapacity(height)
  if (stacked) {
    const visible = widths.slice(0, rows)
    if (widths.length > rows) visible[visible.length - 1] += 4 + badgeWidth
    return Math.min(maximum, Math.max(...visible))
  }
  return smallestWidth(width => {
    let count = 1, used = 0
    for (const size of widths) {
      if (size > width) return false
      if (used && used + 4 + size > width) { count++; used = 0 }
      if (count > rows) return false
      used += (used ? 4 : 0) + size
    }
    return true
  }, maximum)
}
