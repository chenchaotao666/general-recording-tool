import { useZIndex } from 'element-plus'

// Measure only open menus, never subscribe to table/document scrolling.
const cleanup = new WeakMap()
const submenuMinWidths = new WeakMap()
const gap = 8
function viewport() {
  return {
    width: document.documentElement.clientWidth || window.innerWidth,
    height: document.documentElement.clientHeight || window.innerHeight,
  }
}
function clamp(value, size, available) {
  return Math.max(gap, Math.min(value, available - size - gap))
}
function place(el, point) {
  const { width, height } = viewport()
  el.style.left = `${clamp(point.x, el.offsetWidth, width)}px`
  el.style.top = `${clamp(point.y, el.offsetHeight, height)}px`
}

// Fixed descendants escape overflow clipping without breaking DOM hover/focus
// ancestry or outside-click checks. Neither menu may establish a transform.
export function placeSubmenu(sub, item) {
  const { width, height } = viewport()
  if (!submenuMinWidths.has(sub)) submenuMinWidths.set(sub, parseFloat(getComputedStyle(sub).minWidth) || 0)
  Object.assign(sub.style, {
    position: 'fixed', right: 'auto', left: '0px', top: '0px',
    minWidth: `${Math.min(submenuMinWidths.get(sub), Math.max(0, width - gap * 2))}px`,
    maxWidth: `${Math.max(0, width - gap * 2)}px`,
    maxHeight: `${Math.max(0, height - gap * 2)}px`,
    overflow: 'auto',
  })
  const rect = sub.getBoundingClientRect()
  if (!rect.width) return
  const anchor = item.getBoundingClientRect()
  const left = anchor.right - 2 + rect.width <= width - gap ? anchor.right - 2 : anchor.left - rect.width + 2
  sub.style.left = `${clamp(left, rect.width, width)}px`
  sub.style.top = `${clamp(anchor.top - 4, rect.height, height)}px`
}
function placeOpenSubmenus(el) {
  // DOM order positions outer submenus before their nested anchors.
  for (const sub of el.querySelectorAll('.has-sub > .fm-sub')) {
    if (sub.getClientRects().length) placeSubmenu(sub, sub.parentElement)
  }
}

export default {
  mounted(el, binding) {
    // Directive hooks may run outside setup, so use the smart workspace base.
    const layer = el.closest('.fm-mask') || el
    layer.style.zIndex = String(useZIndex(4000).nextZIndex())
    el._menuPoint = binding.value
    const resize = () => { place(el, el._menuPoint); placeOpenSubmenus(el) }
    const reposition = () => placeOpenSubmenus(el)
    place(el, binding.value)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(el)
    window.addEventListener('resize', resize)
    el.addEventListener('mouseenter', reposition, true)
    el.addEventListener('focusin', reposition)
    el.addEventListener('scroll', reposition, true)
    cleanup.set(el, () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
      el.removeEventListener('mouseenter', reposition, true)
      el.removeEventListener('focusin', reposition)
      el.removeEventListener('scroll', reposition, true)
    })
  },
  updated(el, binding) {
    el._menuPoint = binding.value
    place(el, binding.value)
    placeOpenSubmenus(el)
  },
  unmounted(el) {
    cleanup.get(el)?.()
    cleanup.delete(el)
  },
}
