// VXE prioritizes resizeWidth over the column's width prop after manual resizing.
// Apply the targeted widths together and refresh layout once.
export async function applyColumnWidths(table, widths) {
  if (!table) return
  const scroll = table.getScroll()
  let changed = false
  for (const [name, width] of Object.entries(widths)) {
    const column = table.getColumnByField(name)
    if (!column || !Number.isFinite(width) || width <= 0) continue
    column.resizeWidth = width
    changed = true
  }
  if (!changed) return
  await table.refreshColumn()
  await table.scrollTo(scroll.scrollLeft, scroll.scrollTop)
}
