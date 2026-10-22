// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { installScrollbarHover } from '../src/smart/utils/scrollbarHover.js'

test('hover paints a thicker thumb and holds it during drag without rebuilding overflow', () => {
  let frame
  vi.stubGlobal('requestAnimationFrame', fn => { frame = fn; return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => { frame = null })
  const flush = () => { const fn = frame; frame = null; fn?.() }
  const scope = document.createElement('div'), bar = document.createElement('div')
  scope.className = 'st-page'; scope.append(bar); document.body.append(scope)
  Object.defineProperties(bar, {
    offsetWidth: { value: 100 }, clientWidth: { value: 88 }, clientLeft: { value: 0 },
    offsetHeight: { value: 100 }, clientHeight: { value: 100 }, clientTop: { value: 0 },
    scrollWidth: { value: 88 }, scrollHeight: { value: 500 },
  })
  bar.getBoundingClientRect = () => ({ left: 0, right: 100, top: 0, bottom: 100 })
  const overflow = vi.spyOn(bar.style, 'overflow', 'set')
  const dispose = installScrollbarHover()
  try {
    bar.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 95, clientY: 20 }))
    flush()
    expect(bar.style.getPropertyValue('--st-scrollbar-inset')).toBe('1px')
    bar.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, buttons: 1 }))
    scope.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, buttons: 0 }))
    document.dispatchEvent(new MouseEvent('mouseleave')); flush()
    expect(bar.style.getPropertyValue('--st-scrollbar-inset')).toBe('1px')
    scope.dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); flush()
    expect(bar.style.getPropertyValue('--st-scrollbar-inset')).toBe('')
    expect(overflow).not.toHaveBeenCalled()
  } finally { dispose(); scope.remove(); overflow.mockRestore(); vi.unstubAllGlobals() }
})
