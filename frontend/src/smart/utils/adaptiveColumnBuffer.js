export const WIDE_COLUMN_BUFFER = 35
export const NARROW_COLUMN_BUFFER = 1
const RESTORE_IDLE_MS = 1500

// VXE 4.22 keeps virtual bounds outside the reactive config. Update the actual
// column window too; recalculate()/refreshColumn() would relayout the whole grid.
export function applyColumnBuffer(table, size, setConfig) {
  const data = table?.internalData, state = table?.reactData
  const store = data?.scrollXStore, columns = data?.visibleColumn
  if (!store || !columns?.length || !state?.scrollXLoad || state.isScrollXBig
      || data.mergeBodyList?.length || data.mergeFooterList?.length
      || typeof table.updateScrollXData !== 'function') return false
  const left = table.getScroll().scrollLeft
  const frozenWidth = columns.reduce((sum, c) => sum + (c.fixed === 'left' ? c.renderWidth || 0 : 0), 0)
  // Use VXE's cached offsets, never a DOM geometry read during scrolling.
  let lo = 0, hi = columns.length
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2)
    const offset = data.fullColumnIdData?.[columns[mid].id]?.oLeft
    if (offset == null) return false
    if (offset <= left + frozenWidth) lo = mid + 1
    else hi = mid
  }
  const first = lo === columns.length ? lo : Math.max(0, lo - 2)
  const start = Math.max(0, first - 1 - size * 2)
  const end = Math.min(columns.length, first + store.visibleSize + size * 2)
  // Small tables gain nothing from switching; leave their wide buffer intact.
  if (size === NARROW_COLUMN_BUFFER && start <= store.startIndex && end >= Math.min(columns.length, store.endIndex)) return false
  store.preloadSize = size
  store.offsetSize = size
  store.startIndex = start
  store.endIndex = end
  store.visibleStartIndex = first - 1
  store.visibleEndIndex = first + store.visibleSize + 1
  setConfig(size)
  table.updateScrollXData()
  return true
}

export function createAdaptiveColumnBuffer({ getTable, setConfig, now = () => performance.now() }) {
  let narrow = false, started = null, last = -Infinity, samples = 0, timer = 0, horizontalUntil = 0, dragging = false
  function restore() {
    clearTimeout(timer); timer = 0
    started = null; samples = 0; last = -Infinity
    if (narrow) {
      applyColumnBuffer(getTable(), WIDE_COLUMN_BUFFER, setConfig)
      setConfig(WIDE_COLUMN_BUFFER)
      narrow = false
    }
  }
  function idle() {
    timer = 0
    if (dragging) { timer = setTimeout(idle, 300); return }
    const remaining = RESTORE_IDLE_MS - (now() - last)
    if (remaining > 0) { timer = setTimeout(idle, remaining); return }
    restore()
  }
  return {
    beginVerticalDrag() { dragging = true; horizontalUntil = 0 },
    endVerticalDrag() { dragging = false },
    vertical() {
      const time = now()
      if (time < horizontalUntil) return
      if (started == null || (!dragging && time - last > 300)) { started = time; samples = 0 }
      last = time; samples++
      if (!narrow && samples >= 3 && time - started >= 180) {
        narrow = applyColumnBuffer(getTable(), NARROW_COLUMN_BUFFER, setConfig)
        if (narrow && !timer) timer = setTimeout(idle, RESTORE_IDLE_MS)
      }
    },
    horizontal() { dragging = false; horizontalUntil = now() + 300; restore() },
    restore,
    dispose() { clearTimeout(timer); timer = 0; narrow = false; started = null; last = -Infinity; samples = 0; dragging = false },
  }
}
