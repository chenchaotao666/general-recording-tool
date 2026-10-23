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
    expect(panel.style.left).toBe('200px')
    expect(panel.style.top).toBe('140px')
    expect(panel.dataset.panelDragged).toBe('true')
    pointer(panel, 'pointermove', -500, -500)
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
  expect(panel.style.left).toBe('140px')
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
