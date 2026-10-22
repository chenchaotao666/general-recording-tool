// Pack complete 24px tags into the available cell area, reserving +N on the last row.
export function fitTagRows(widths, width, height, { stacked = false, badgeWidth = 28, gap = 4, tagHeight = 24 } = {}) {
  if (!widths.length || width <= 0) return []
  const capacity = Math.max(1, Math.floor((height + gap) / (tagHeight + gap)))
  const rows = [[]]
  let used = 0
  for (let index = 0; index < widths.length; index++) {
    const size = Math.min(width, widths[index])
    let row = rows.at(-1)
    if (row.length && (stacked || used + gap + size > width + .5)) {
      if (rows.length >= capacity) break
      rows.push([]); row = rows.at(-1); used = 0
    }
    row.push({ index, width: size })
    used += (row.length > 1 ? gap : 0) + size
  }
  if (rows.flat().length === widths.length) return rows
  const last = rows.at(-1)
  while (last.length) {
    const before = last.slice(0, -1).reduce((sum, item) => sum + item.width + gap, 0)
    const room = width - before - gap - badgeWidth
    if (room >= Math.min(12, last.at(-1).width) || last.length === 1) {
      last.at(-1).width = Math.max(0, Math.min(last.at(-1).width, room))
      break
    }
    last.pop()
  }
  return rows
}
