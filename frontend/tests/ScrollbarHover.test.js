// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { installScrollbarHover } from '../src/smart/utils/scrollbarHover.js'

test('native scrollbar is not rebuilt when a held drag leaves its track', () => {
  let frame
  vi.stubGlobal('requestAnimationFrame', fn => { frame = fn; return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => { frame = null })
  const flush = () => { const fn = frame; frame = null; fn?.() }
  const scope = document.createElement('div'), bar = document.createElement('div')
  scope.className = 'st-page'; scope.append(bar); document.body.append(scope)
  Object.defineProperties(bar, {
    offsetWidth: { value: 100 }, clientWidth: { value: 100 }, clientLeft: { value: 0 },
    offsetHeight: { value: 12 }, clientHeight: { value: 0 }, clientTop: { value: 0 },
    scrollWidth: { value: 500 }, scrollHeight: { value: 0 },
  })
  bar.getBoundingClientRect = () => ({ left: 0, right: 100, top: 100, bottom: 112 })
  const overflow = vi.spyOn(bar.style, 'overflow', 'set')
  installScrollbarHover()
  try {
    bar.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 50, clientY: 106 }))
    flush()
    expect(bar.classList.contains('sb-hot')).toBe(true)
    overflow.mockClear()
    bar.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, buttons: 1 }))
    // Native scrollbar interactions may report zero buttons in later move events.
    scope.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, buttons: 0, clientY: 30 }))
    document.dispatchEvent(new MouseEvent('mouseleave'))
    flush()
    expect(overflow).not.toHaveBeenCalled()
    expect(bar.classList.contains('sb-hot')).toBe(true)
    scope.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientY: 30 }))
    expect(overflow).not.toHaveBeenCalled()
    flush()
    expect(bar.classList.contains('sb-hot')).toBe(false)
    expect(overflow).toHaveBeenCalled()
  } finally { scope.remove(); overflow.mockRestore(); vi.unstubAllGlobals() }
})
