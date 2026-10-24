const states = new WeakMap()
const interactive = 'input, textarea, button, select, a, [role="button"], .st-icon-action, .el-select, [contenteditable="true"]'
const margin = 12
const dragThreshold = 4

function clamp(value, size, viewport) {
  return Math.max(margin, Math.min(value, viewport - size - margin))
}

// A new opening/anchor starts a new placement session, even if Vue reuses the DOM.
export function resetPanelDrag(element) {
  states.get(element)?.reset()
}

// 拖动真实面板节点，不改变触发点；表单控件仍保留各自的点击、选字行为。
export const vPanelDrag = {
  mounted(element, binding) {
    const state = { options: binding.value || {}, drag: null, panel: null, frame: 0 }
    const flush = () => {
      state.frame = 0
      const drag = state.drag
      if (!drag?.moved) return
      state.panel.style.transform = `translate3d(${drag.left - drag.baseLeft}px, ${drag.top - drag.baseTop}px, 0)`
    }
    const stop = event => {
      const drag = state.drag
      if (!drag || (event?.pointerId != null && event.pointerId !== drag.id)) return
      cancelAnimationFrame(state.frame); state.frame = 0
      if (drag.moved) {
        // Commit the latest pointer position even if its animation frame hasn't run.
        state.position = { left: drag.left, top: drag.top }
        Object.assign(state.panel.style, {
          left: `${drag.left}px`, top: `${drag.top}px`, transform: 'none',
          willChange: drag.willChange,
        })
        delete state.panel.dataset.panelDragging
        state.panel.style.transition = drag.transition
      }
      state.drag = null
      if (element.hasPointerCapture?.(drag.id)) element.releasePointerCapture(drag.id)
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
      if (state.drag || event.button !== 0 || event.target.closest(interactive)) return
      const handle = event.target.closest(state.options.handle || '[data-panel-drag-handle]')
      if (!handle || !element.contains(handle)) return
      const panel = state.options.panel ? element.closest(state.options.panel) : element
      if (!panel) return
      event.preventDefault()
      const rect = panel.getBoundingClientRect()
      if (!state.initialStyle) state.initialStyle = Object.fromEntries(
        ['position', 'margin', 'transform'].map(key => [key, panel.style[key]]))
      state.panel = panel
      state.drag = {
        id: event.pointerId, x: event.clientX, y: event.clientY,
        originLeft: rect.left, originTop: rect.top,
        baseLeft: clamp(rect.left, rect.width, window.innerWidth),
        baseTop: clamp(rect.top, rect.height, window.innerHeight),
        width: rect.width, height: rect.height, viewportWidth: window.innerWidth, viewportHeight: window.innerHeight,
        willChange: panel.style.willChange, transition: panel.style.transition, moved: false,
      }
      element.setPointerCapture?.(event.pointerId)
    }
    const move = event => {
      const drag = state.drag
      if (!drag || event.pointerId !== drag.id) return
      if (!drag.moved && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < dragThreshold) return
      if (!drag.moved) {
        drag.moved = true
        state.panel.dataset.panelDragged = 'true'
        state.panel.dataset.panelDragging = 'true'
        Object.assign(state.panel.style, {
          position: 'fixed', margin: '0', left: `${drag.baseLeft}px`, top: `${drag.baseTop}px`,
          transform: 'none', willChange: 'transform', transition: 'none',
        })
      }
      event.preventDefault()
      drag.left = clamp(drag.originLeft + event.clientX - drag.x, drag.width, drag.viewportWidth)
      drag.top = clamp(drag.originTop + event.clientY - drag.y, drag.height, drag.viewportHeight)
      if (!state.frame) state.frame = requestAnimationFrame(flush)
    }
    const resize = () => {
      stop()
      if (!state.panel?.isConnected || !state.panel.getClientRects().length) return
      const rect = state.panel.getBoundingClientRect()
      place(state.panel, rect.left, rect.top)
    }
    element.addEventListener('pointerdown', down)
    element.addEventListener('pointermove', move)
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) element.addEventListener(name, stop)
    window.addEventListener('resize', resize)
    window.addEventListener('blur', stop)
    state.cleanup = () => {
      stop()
      element.removeEventListener('pointerdown', down)
      element.removeEventListener('pointermove', move)
      for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) element.removeEventListener(name, stop)
      window.removeEventListener('resize', resize)
      window.removeEventListener('blur', stop)
      if (state.panel) delete state.panel.dataset.panelDragged
    }
    state.restore = () => {
      if (!state.drag && state.position && state.panel) place(state.panel, state.position.left, state.position.top)
    }
    state.reset = () => {
      stop()
      if (state.panel) {
        Object.assign(state.panel.style, state.initialStyle || {})
        state.panel.style.removeProperty('left')
        state.panel.style.removeProperty('top')
        delete state.panel.dataset.panelDragged
        delete state.panel.dataset.panelDragging
      }
      state.position = null
      state.initialStyle = null
      state.panel = null
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
