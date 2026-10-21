// Measure only when opening/repositioning a menu, never during table scrolling.
const cleanup = new WeakMap()
function place(el, point) {
  const gap = 8
  const width = document.documentElement.clientWidth
  const height = document.documentElement.clientHeight
  el.style.left = `${Math.max(gap, Math.min(point.x, width - el.offsetWidth - gap))}px`
  el.style.top = `${Math.max(gap, Math.min(point.y, height - el.offsetHeight - gap))}px`
}

export default {
  mounted(el, binding) {
    el._menuPoint = binding.value
    const resize = () => place(el, el._menuPoint)
    const hover = event => {
      const item = event.target.closest?.('.has-sub')
      if (!item || !el.contains(item) || item.contains(event.relatedTarget)) return
      const sub = Array.from(item.children).find(child => child.classList.contains('fm-sub'))
      if (!sub) return
      sub.style.left = ''
      sub.style.right = ''
      sub.style.top = ''
      const rect = sub.getBoundingClientRect()
      if (!rect.width) return
      const width = document.documentElement.clientWidth
      if (rect.right > width - 8) {
        sub.style.left = 'auto'
        sub.style.right = 'calc(100% - 2px)'
      }
      const positioned = sub.getBoundingClientRect()
      if (positioned.left < 8) {
        sub.style.right = 'auto'
        sub.style.left = `${8 - item.getBoundingClientRect().left}px`
      }
      const overflow = rect.bottom - (document.documentElement.clientHeight - 8)
      if (overflow > 0) sub.style.top = `${-4 - Math.min(overflow, rect.top - 8)}px`
    }
    place(el, binding.value)
    window.addEventListener('resize', resize)
    el.addEventListener('mouseover', hover)
    cleanup.set(el, () => {
      window.removeEventListener('resize', resize)
      el.removeEventListener('mouseover', hover)
    })
  },
  updated(el, binding) {
    el._menuPoint = binding.value
    place(el, binding.value)
  },
  unmounted(el) {
    cleanup.get(el)?.()
    cleanup.delete(el)
  },
}
