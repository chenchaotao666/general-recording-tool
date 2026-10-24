// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { vPanelDrag } from '../src/smart/utils/panelDrag.js'

function pointer(element, type, x, y) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  element.dispatchEvent(event)
}

test('panel drag preserves input interaction, clamps bounds and stops after release', () => {
  const panel = document.createElement('div')
  panel.innerHTML = '<header><span>Title</span><input /><button>Close</button></header>'
  document.body.append(panel)
  panel.getBoundingClientRect = () => ({ left: 100, top: 80, width: 320, height: 200 })
  panel.setPointerCapture = vi.fn()
  vPanelDrag.mounted(panel, { value: { handle: 'header' } })
  try {
    pointer(panel.querySelector('input'), 'pointerdown', 120, 90)
    pointer(panel, 'pointermove', 300, 200)
    expect(panel.style.left).toBe('')
    pointer(panel.querySelector('span'), 'pointerdown', 120, 90)
    pointer(panel, 'pointermove', 220, 150)
    pointer(panel, 'pointerup', 220, 150)
    expect(panel.style.left).toBe('200px')
    expect(panel.style.top).toBe('140px')
    expect(panel.dataset.panelDragged).toBe('true')
    pointer(panel.querySelector('span'), 'pointerdown', 120, 90)
    pointer(panel, 'pointermove', -500, -500)
    pointer(panel, 'pointerup', -500, -500)
    expect(panel.style.left).toBe('12px')
    expect(panel.style.top).toBe('12px')
    pointer(panel, 'pointerup', -500, -500)
    pointer(panel, 'pointermove', 600, 400)
    expect(panel.style.left).toBe('12px')
  } finally {
    vPanelDrag.beforeUnmount(panel)
    panel.remove()
  }
})

test('dialog body handle moves its dialog and cleans up when closed mid-drag', () => {
  const panel = document.createElement('div')
  panel.className = 'el-dialog'
  panel.innerHTML = '<div class="body"><div data-panel-drag-handle>Move</div></div>'
  document.body.append(panel)
  panel.getBoundingClientRect = () => ({ left: 100, top: 80, width: 320, height: 200 })
  const body = panel.querySelector('.body')
  vPanelDrag.mounted(body, { value: { panel: '.el-dialog' } })
  pointer(body.firstChild, 'pointerdown', 100, 80)
  pointer(body, 'pointermove', 140, 110)
  expect(panel.style.left).toBe('100px')
  vPanelDrag.beforeUnmount(body)
  pointer(body, 'pointermove', 200, 160)
  expect(panel.style.left).toBe('140px')
  expect(panel.dataset.panelDragged).toBeUndefined()
  panel.remove()
})

test('clicking a drag handle or moving below threshold does not reposition the panel', () => {
  const panel = document.createElement('div')
  panel.innerHTML = '<div data-panel-drag-handle>Move</div>'
  panel.style.cssText = 'left: 8px; top: 9px; transform: translateY(2px)'
  document.body.append(panel)
  panel.getBoundingClientRect = () => ({ left: 8, top: 11, width: 320, height: 200 })
  vPanelDrag.mounted(panel, { value: {} })
  const original = panel.style.cssText
  pointer(panel.firstChild, 'pointerdown', 100, 80)
  pointer(panel, 'pointermove', 101, 81)
  pointer(panel, 'pointerup', 101, 81)
  expect(panel.style.cssText).toBe(original)
  expect(panel.dataset.panelDragged).toBeUndefined()
  vPanelDrag.beforeUnmount(panel)
  panel.remove()
})

test('dragging batches transforms without repeated layout reads and commits the last move', () => {
  const frames = new Map()
  let frameId = 0
  vi.stubGlobal('requestAnimationFrame', fn => { frames.set(++frameId, fn); return frameId })
  vi.stubGlobal('cancelAnimationFrame', id => frames.delete(id))
  const panel = document.createElement('div')
  panel.className = 'el-dialog'
  panel.innerHTML = '<div class="body"><div data-panel-drag-handle></div><input></div>'
  document.body.append(panel)
  const body = panel.firstElementChild, handle = body.firstElementChild
  const bounds = vi.spyOn(panel, 'getBoundingClientRect').mockReturnValue({ left: 100, top: 100, width: 320, height: 300 })
  body.setPointerCapture = vi.fn(); body.hasPointerCapture = () => true; body.releasePointerCapture = vi.fn()
  const pointer = (target, type, x, y) => {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 })
    Object.defineProperty(event, 'pointerId', { value: 1 })
    target.dispatchEvent(event)
  }
  const binding = { value: { panel: '.el-dialog' } }
  vPanelDrag.mounted(body, binding)
  try {
    pointer(body.querySelector('input'), 'pointerdown', 110, 110)
    expect(bounds).not.toHaveBeenCalled()
    pointer(handle, 'pointerdown', 110, 110)
    pointer(body, 'pointermove', 112, 112)
    expect(frames.size).toBe(0)
    pointer(body, 'pointermove', 130, 140)
    pointer(body, 'pointermove', 150, 170)
    vPanelDrag.updated(body, binding)
    expect(bounds).toHaveBeenCalledTimes(1)
    expect(frames.size).toBe(1)
    const jobs = [...frames.values()]; frames.clear(); jobs.forEach(fn => fn())
    expect(panel.style.transform).toBe('translate3d(40px, 60px, 0)')
    expect(panel.style.left).toBe('100px')
    pointer(body, 'pointermove', 160, 180)
    pointer(body, 'pointerup', 160, 180)
    expect(panel.style.left).toBe('150px')
    expect(panel.style.top).toBe('170px')
    expect(panel.style.transform).toBe('none')
    expect(panel.style.willChange).toBe('')
    expect(panel.dataset.panelDragging).toBeUndefined()
    expect(frames.size).toBe(0)
    expect(bounds).toHaveBeenCalledTimes(1)
    // A later drag still clamps to the viewport and finishes on focus loss.
    pointer(handle, 'pointerdown', 110, 110)
    pointer(body, 'pointermove', -1000, -1000)
    window.dispatchEvent(new Event('blur'))
    expect(panel.style.left).toBe('12px')
    expect(panel.style.top).toBe('12px')
    expect(frames.size).toBe(0)
  } finally {
    vPanelDrag.beforeUnmount(body); panel.remove(); vi.unstubAllGlobals()
  }
})
