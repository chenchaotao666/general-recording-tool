// Chromium does not reliably repaint scrollbar pseudo-class hover changes.
// Updating the paint variables does, without toggling overflow or scroll position.
const scope = 'body:has(.st-page, .smart-home, .dash-page, .smart-dash), .st-tbpanel, .st-pop, .st-fcd, .sel-panel, .cell-overlay, .people-picker-pop, .contact-picker-dialog'
export function installScrollbarHover() {
  let hot = null, pressed = false, frame = 0, lastEvent = null
  const vars = ['--st-scrollbar-inset', '--st-scrollbar-thumb']
  function setHot(el) {
    if (hot?.el === el) return
    if (hot) vars.forEach((key, i) => {
      const [value, priority] = hot.previous[i]
      if (value) hot.el.style.setProperty(key, value, priority)
      else hot.el.style.removeProperty(key)
    })
    hot = el ? { el, previous: vars.map(key => [el.style.getPropertyValue(key), el.style.getPropertyPriority(key)]) } : null
    if (el) {
      el.style.setProperty(vars[0], '1px')
      el.style.setProperty(vars[1], 'var(--st-scrollbar-thumb-hover)')
    }
  }
  function check() {
    frame = 0
    if (pressed || lastEvent?.buttons) return
    const e = lastEvent, el = e?.target instanceof Element ? e.target : null
    if (!el?.closest(scope)) { setHot(null); return }
    const vertical = el.offsetWidth - el.clientWidth - el.clientLeft * 2 > 0 && el.scrollHeight > el.clientHeight
    const horizontal = el.offsetHeight - el.clientHeight - el.clientTop * 2 > 0 && el.scrollWidth > el.clientWidth
    if (!vertical && !horizontal) { setHot(null); return }
    const rect = el.getBoundingClientRect()
    const onVertical = vertical && e.clientX >= rect.left + el.clientLeft + el.clientWidth && e.clientX <= rect.right
    const onHorizontal = horizontal && e.clientY >= rect.top + el.clientTop + el.clientHeight && e.clientY <= rect.bottom
    setHot(onVertical || onHorizontal ? el : null)
  }
  function move(event) {
    lastEvent = event
    if (!pressed && !event.buttons && !frame) frame = requestAnimationFrame(check)
  }
  function down() { pressed = true; cancelAnimationFrame(frame); frame = 0 }
  function up(event) { pressed = false; move(event) }
  function leave() { if (!pressed) setHot(null) }
  function blur() { pressed = false; cancelAnimationFrame(frame); frame = 0; setHot(null) }
  document.addEventListener('mousemove', move, { passive: true })
  document.addEventListener('mousedown', down, true)
  document.addEventListener('mouseup', up, true)
  document.addEventListener('mouseleave', leave)
  window.addEventListener('blur', blur)
  return () => {
    blur()
    document.removeEventListener('mousemove', move)
    document.removeEventListener('mousedown', down, true)
    document.removeEventListener('mouseup', up, true)
    document.removeEventListener('mouseleave', leave)
    window.removeEventListener('blur', blur)
  }
}
