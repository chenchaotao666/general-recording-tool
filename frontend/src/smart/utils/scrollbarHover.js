// 智能表格滚动条悬停加粗（样式见 smart/tokens.css 的 .sb-hot）。
// Chrome 不会因 :hover / 类名变化重绘 ::-webkit-scrollbar 自定义滚动条，纯 CSS 的「移上去变粗」不生效。
// 这里在指针进入某个滚动容器的滚动条区域时打 .sb-hot 并强制重建滚动条；离开（拖动中则等松开）时撤销。
// 只作用于智能表格范围内的容器（与 tokens.css 的滚动条样式同一范围）。

const SCOPE = '.smart-home, .st-page, .dash-page, .st-tbpanel, .st-pop, .sel-panel, .cell-overlay'

let hot = null   // {el, axis}
let raf = 0
let lastEvt = null
let mouseDown = false

// 切换 overflow 让浏览器重建滚动条（滚动位置先记下再还原，避免跳动）
function repaint(el) {
  const { scrollTop, scrollLeft } = el
  const prev = el.style.overflow
  el.style.overflow = 'hidden'
  void el.offsetWidth
  el.style.overflow = prev
  el.scrollTop = scrollTop
  el.scrollLeft = scrollLeft
}

function setHot(next) {
  // Rebuilding a native scrollbar during a held press loses its drag capture.
  if (mouseDown) return
  if (hot?.el === next?.el) return
  if (hot) { hot.el.classList.remove('sb-hot'); repaint(hot.el) }
  hot = next
  if (hot) { hot.el.classList.add('sb-hot'); repaint(hot.el) }
}

// 指针是否落在 el 自身的滚动条区域（竖向在右侧、横向在底部；内容区 clientWidth/clientHeight 之外）
function scrollbarHit(el, x, y) {
  const r = el.getBoundingClientRect()
  const left = r.left + el.clientLeft
  const top = r.top + el.clientTop
  const vBar = el.offsetWidth - el.clientWidth - el.clientLeft * 2 > 0 && el.scrollHeight > el.clientHeight
  const hBar = el.offsetHeight - el.clientHeight - el.clientTop * 2 > 0 && el.scrollWidth > el.clientWidth
  if (vBar && x >= left + el.clientWidth && x <= r.right && y >= r.top && y <= r.bottom) return true
  if (hBar && y >= top + el.clientHeight && y <= r.bottom && x >= r.left && x <= r.right) return true
  return false
}

function check() {
  raf = 0
  const e = lastEvt
  if (!e) return
  if (mouseDown || e.buttons) return
  const el = e.target instanceof Element ? e.target : null
  const inScope = el?.closest?.(SCOPE)
  setHot(inScope && scrollbarHit(el, e.clientX, e.clientY) ? { el } : null)
}

function onMove(e) {
  lastEvt = e
  if (mouseDown || e.buttons) return
  if (!raf) raf = requestAnimationFrame(check)
}
function onDown() {
  mouseDown = true
  cancelAnimationFrame(raf)
  raf = 0
}
function onUp(e) {
  mouseDown = false
  lastEvt = e
  // Wait until the browser has finished releasing the native scrollbar.
  if (!raf) raf = requestAnimationFrame(check)
}

let installed = false
export function installScrollbarHover() {
  if (installed || typeof document === 'undefined') return
  installed = true
  document.addEventListener('mousedown', onDown, true)
  document.addEventListener('mousemove', onMove, { passive: true })
  document.addEventListener('mouseup', onUp, true)
  document.addEventListener('mouseleave', () => setHot(null))
  window.addEventListener('blur', () => {
    mouseDown = false
    cancelAnimationFrame(raf); raf = 0; lastEvt = null
    setHot(null)
  })
}
