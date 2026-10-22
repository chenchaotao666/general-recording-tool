// Compact insertion feedback leaves list geometry and native drop targets intact.
// Forms explicitly retain their full-height placeholder feedback.
const rows = new WeakMap()
let session = null
function removePlaceholder() {
  if (!session) return
  session.placeholder?.remove()
  session.destination?.classList.remove('st-reorder-before', 'st-reorder-after', 'st-reorder-horizontal')
  session.placeholder = null
  session.destination = null
}
function stop() {
  if (!session) return
  const source = session.source
  session.into?.classList.remove('st-reorder-into')
  cancelAnimationFrame(session.frame)
  removePlaceholder()
  source.classList.remove('st-reorder-source')
  session = null
  document.removeEventListener('drop', finish, true)
  document.removeEventListener('dragend', stop, true)
  document.removeEventListener('dragover', outside, true)
  window.removeEventListener('blur', stop)
}
// Keep the placeholder alive until the target's drop handler has run.
function finish() { queueMicrotask(stop) }
function outside(event) {
  if (!session || session.placeholder?.contains(event.target)) return
  if (!event.target.closest?.('[data-st-reorder]')) {
    removePlaceholder()
    session.into?.classList.remove('st-reorder-into')
    session.into = null
  }
}
function paint(el) {
  const value = rows.get(el)?.value
  const indicator = typeof value === 'string' ? value : value?.indicator
  if (!session || !indicator) {
    if (session?.destination === el) removePlaceholder()
    return
  }
  const into = indicator.includes('into')
  const before = indicator.includes('before')
  const append = indicator === 'append'
  if (!into && !before && !append && !indicator.includes('after')) return
  // Group membership uses the row itself as the drop zone.
  el.classList.toggle('st-reorder-into', into)
  if (session.into && session.into !== el) session.into.classList.remove('st-reorder-into')
  session.into = into ? el : null
  if (into) { removePlaceholder(); return }
  if (session.destination === el && session.position === indicator) return
  removePlaceholder()
  session.destination = el
  session.position = indicator
  if (!value?.placeholder) {
    el.classList.add(before ? 'st-reorder-before' : 'st-reorder-after')
    el.classList.toggle('st-reorder-horizontal', !!value?.horizontal)
    return
  }
  const placeholder = document.createElement('div')
  placeholder.className = 'st-reorder-placeholder'
  placeholder.setAttribute('aria-hidden', 'true')
  placeholder.style.height = `${session.height}px`
  if (value?.horizontal) placeholder.style.width = `${session.width}px`
  const target = session.lastOver || el
  placeholder.addEventListener('dragover', event => {
    event.preventDefault(); event.stopPropagation()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  })
  placeholder.addEventListener('drop', event => {
    event.preventDefault(); event.stopPropagation()
    target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true,
      dataTransfer: event.dataTransfer, clientX: event.clientX, clientY: event.clientY }))
    stop()
  })
  if (append) el.append(placeholder)
  else el.parentElement?.insertBefore(placeholder, before ? el : el.nextSibling)
  session.placeholder = placeholder
  session.destination = el
  session.position = indicator
}
export const vReorderFeedback = {
  mounted(el, binding) {
    el.dataset.stReorder = ''
    const start = event => {
      if (event.target.closest('[data-st-reorder]') !== el) return
      stop()
      const rect = el.getBoundingClientRect()
      session = { source: el, height: Math.max(32, Math.min(300, rect.height)), width: rect.width,
        lastOver: null, placeholder: null, destination: null, frame: 0 }
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move'
        if (!event.dataTransfer.types.includes('text/plain')) event.dataTransfer.setData('text/plain', 'reorder')
        event.dataTransfer.setDragImage(el, Math.min(24, rect.width / 2), Math.min(24, rect.height / 2))
      }
      session.frame = requestAnimationFrame(() => { if (session?.source === el) el.classList.add('st-reorder-source') })
      document.addEventListener('drop', finish, true)
      document.addEventListener('dragend', stop, true)
      document.addEventListener('dragover', outside, true)
      window.addEventListener('blur', stop)
    }
    const over = event => {
      if (!session) return
      session.lastOver = el
      // Vue commits the component's existing before/after indicator first.
      queueMicrotask(() => paint(el))
    }
    rows.set(el, { value: binding.value, start, over })
    el.addEventListener('dragstart', start, true)
    el.addEventListener('dragover', over, true)
  },
  updated(el, binding) {
    const row = rows.get(el)
    if (row) row.value = binding.value
    el.classList.remove('st-reorder-into')
    paint(el)
  },
  beforeUnmount(el) {
    const row = rows.get(el)
    if (session?.source === el || session?.destination === el || session?.into === el) stop()
    el.removeEventListener('dragstart', row?.start, true)
    el.removeEventListener('dragover', row?.over, true)
    rows.delete(el)
  },
}
