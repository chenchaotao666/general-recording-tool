// Layout work is coalesced and suspended while the grid is scrolling.
export function createGridLayoutQueue() {
  const pending = new Set()
  const widths = new Map()
  // Bounded, grid-local cache survives virtual cell unmounts, not grid disposal.
  const tagLayouts = new Map()
  let observer
  let paused = false, frame = 0
  function schedule() {
    if (paused || frame || !pending.size) return
    frame = requestAnimationFrame(() => {
      frame = 0
      if (paused) return
      const jobs = [...pending]
      pending.clear()
      jobs.forEach(job => job())
    })
  }
  return {
    get paused() { return paused },
    enqueue(job) { pending.add(job); schedule() },
    cancel(job) { pending.delete(job) },
    getTagLayout(key) {
      const value = tagLayouts.get(key)
      if (value) { tagLayouts.delete(key); tagLayouts.set(key, value) }
      return value
    },
    setTagLayout(key, value) {
      tagLayouts.delete(key)
      tagLayouts.set(key, value)
      if (tagLayouts.size > 1024) tagLayouts.delete(tagLayouts.keys().next().value)
    },
    observeWidth(element, changed) {
      if (!observer) observer = new ResizeObserver(entries => {
        for (const entry of entries) {
          const item = widths.get(entry.target)
          if (!item || Math.abs(entry.contentRect.width - item.width) < .5) continue
          item.width = entry.contentRect.width
          item.changed(item.width)
        }
      })
      widths.set(element, { width: -1, changed })
      observer.observe(element)
      return () => {
        widths.delete(element)
        observer?.unobserve(element)
        if (!widths.size) { observer?.disconnect(); observer = null }
      }
    },
    pause() { paused = true; cancelAnimationFrame(frame); frame = 0 },
    resume() { paused = false; schedule() },
    dispose() {
      cancelAnimationFrame(frame); frame = 0; pending.clear()
      observer?.disconnect(); observer = null; widths.clear()
      tagLayouts.clear()
    },
  }
}
