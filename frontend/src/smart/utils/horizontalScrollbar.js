// Keep VXE's scroll element and synchronization, but own the thumb gesture.
// Native Windows scrollbars can cancel a drag when the pointer moves off-track.
export function installHorizontalScrollbar(handle, options) {
  return installScrollbar(handle, 'horizontal', options)
}
export function installVerticalScrollbar(handle, options) {
  return installScrollbar(handle, 'vertical', options)
}
function installScrollbar(handle, axis, { onStart, onEnd } = {}) {
  const vertical = axis === 'vertical'
  const position = vertical ? 'scrollTop' : 'scrollLeft'
  const clientSize = vertical ? 'clientHeight' : 'clientWidth'
  const scrollSize = vertical ? 'scrollHeight' : 'scrollWidth'
  const coordinate = vertical ? 'clientY' : 'clientX'
  const track = document.createElement('div')
  const thumb = document.createElement('div')
  track.className = `st-${axis}-track`
  thumb.className = `st-${axis}-thumb`
  track.append(thumb)
  handle.parentElement.append(track)
  const opacity = handle.style.opacity
  handle.style.opacity = '0'
  track.tabIndex = 0
  track.setAttribute('role', 'scrollbar')
  track.setAttribute('aria-label', vertical ? '纵向滚动' : '横向滚动')
  track.setAttribute('aria-orientation', axis)
  track.setAttribute('aria-valuemin', '0')
  let max = 0, travel = 0, thumbSize = 0, drag = null
  let frame = 0, pending = null, lastTransform = '', lastValue = ''
  function sync() {
    const current = handle[position]
    const transform = `translate${vertical ? 'Y' : 'X'}(${max ? current / max * travel : 0}px)`
    const value = String(Math.round(current))
    if (transform !== lastTransform) { thumb.style.transform = transform; lastTransform = transform }
    if (value !== lastValue) { track.setAttribute('aria-valuenow', value); lastValue = value }
  }
  function flush() {
    frame = 0
    if (pending == null) return
    const next = pending
    pending = null
    if (handle[position] !== next) handle[position] = next
    sync()
  }
  function resize() {
    const width = handle[clientSize]
    max = Math.max(0, handle[scrollSize] - width)
    thumbSize = Math.min(width, Math.max(24, width * width / (handle[scrollSize] || 1)))
    travel = Math.max(0, width - thumbSize)
    thumb.style[vertical ? 'height' : 'width'] = `${thumbSize}px`
    track.style.display = max > 0 ? '' : 'none'
    track.setAttribute('aria-valuemax', String(max))
    sync()
  }
  function down(event) {
    if (event.button !== 0 || !max || !travel) return
    event.preventDefault()
    onStart?.(event)
    // Dimensions are read once at gesture start, never on pointermove.
    if (event.target !== thumb) {
      handle[position] = Math.max(0, Math.min(max,
        (event[coordinate] - track.getBoundingClientRect()[vertical ? 'top' : 'left'] - thumbSize / 2) / travel * max))
    }
    drag = { id: event.pointerId, x: event[coordinate], left: handle[position], scale: max / travel }
    track.setPointerCapture(event.pointerId)
    track.classList.add('dragging')
    sync()
  }
  function move(event) {
    if (!drag || event.pointerId !== drag.id) return
    event.preventDefault()
    // Movement perpendicular to the scrollbar never cancels the gesture.
    pending = Math.max(0, Math.min(max, drag.left + (event[coordinate] - drag.x) * drag.scale))
    if (!frame) frame = requestAnimationFrame(flush)
  }
  function end(event) {
    if (!drag || (event?.pointerId != null && event.pointerId !== drag.id)) return
    cancelAnimationFrame(frame)
    flush()
    const id = drag.id
    drag = null
    if (track.hasPointerCapture(id)) track.releasePointerCapture(id)
    track.classList.remove('dragging')
    onEnd?.()
  }
  function keydown(event) {
    const next = { [vertical ? 'ArrowUp' : 'ArrowLeft']: handle[position] - 40,
      [vertical ? 'ArrowDown' : 'ArrowRight']: handle[position] + 40, Home: 0, End: max }[event.key]
    if (next == null) return
    event.preventDefault()
    handle[position] = Math.max(0, Math.min(max, next))
    sync()
  }
  track.addEventListener('pointerdown', down)
  track.addEventListener('pointermove', move)
  track.addEventListener('pointerup', end)
  track.addEventListener('pointercancel', end)
  track.addEventListener('lostpointercapture', end)
  track.addEventListener('keydown', keydown)
  handle.addEventListener('scroll', sync, { passive: true })
  window.addEventListener('blur', end)
  const observer = new ResizeObserver(resize)
  observer.observe(handle)
  if (handle.firstElementChild) observer.observe(handle.firstElementChild)
  resize()
  return () => {
    end()
    observer.disconnect()
    handle.removeEventListener('scroll', sync)
    window.removeEventListener('blur', end)
    handle.style.opacity = opacity
    track.remove()
  }
}
