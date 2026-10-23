const states = new WeakMap()
const interactive = 'input, textarea, button, select, a, [role="button"], .st-icon-action, .el-select, [contenteditable="true"]'
const margin = 12
const dragThreshold = 4

function clamp(value, size, viewport) {
  return Math.max(margin, Math.min(value, viewport - size - margin))
}

// 拖动真实面板节点，不改变触发点；表单控件仍保留各自的点击、选字行为。
export const vPanelDrag = {
  mounted(element, binding) {
    const state = { options: binding.value || {}, drag: null, panel: null }
    const stop = () => {
      const drag = state.drag
      state.drag = null
      if (drag && element.hasPointerCapture?.(drag.id)) element.releasePointerCapture(drag.id)
    }
    const place = (panel, left, top) => {
      const rect = panel.getBoundingClientRect()
      state.position = {
        left: clamp(left, rect.width, window.innerWidth),
        top: clamp(top, rect.height, window.innerHeight),
      }
      Object.assign(panel.style, {
        position: 'fixed', margin: '0', transform: 'none',
        left: `${state.position.left}px`, top: `${state.position.top}px`,
      })
    }
    const down = event => {
      if (event.button !== 0 || event.target.closest(interactive)) return
      const handle = event.target.closest(state.options.handle || '[data-panel-drag-handle]')
      if (!handle || !element.contains(handle)) return
      const panel = state.options.panel ? element.closest(state.options.panel) : element
      if (!panel) return
      event.preventDefault()
      const rect = panel.getBoundingClientRect()
      state.panel = panel
      state.drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top, moved: false }
      element.setPointerCapture?.(event.pointerId)
    }
    const move = event => {
      const drag = state.drag
      if (!drag || event.pointerId !== drag.id) return
      if (!drag.moved && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < dragThreshold) return
      drag.moved = true
      state.panel.dataset.panelDragged = 'true'
      event.preventDefault()
      place(state.panel, drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y)
    }
    const resize = () => {
      if (!state.panel?.isConnected || !state.panel.getClientRects().length) return
      const rect = state.panel.getBoundingClientRect()
      place(state.panel, rect.left, rect.top)
    }
    element.addEventListener('pointerdown', down)
    element.addEventListener('pointermove', move)
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) element.addEventListener(name, stop)
    window.addEventListener('resize', resize)
    state.cleanup = () => {
      stop()
      element.removeEventListener('pointerdown', down)
      element.removeEventListener('pointermove', move)
      for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) element.removeEventListener(name, stop)
      window.removeEventListener('resize', resize)
      if (state.panel) delete state.panel.dataset.panelDragged
    }
    state.restore = () => {
      if (state.position && state.panel) place(state.panel, state.position.left, state.position.top)
    }
    states.set(element, state)
  },
  updated(element, binding) {
    const state = states.get(element)
    if (state) {
      state.options = binding.value || {}
      state.restore()
    }
  },
  beforeUnmount(element) {
    states.get(element)?.cleanup()
    states.delete(element)
  },
}
