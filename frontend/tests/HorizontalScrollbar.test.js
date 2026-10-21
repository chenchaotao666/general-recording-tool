// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { installHorizontalScrollbar, installVerticalScrollbar } from '../src/smart/utils/horizontalScrollbar.js'

test.each(['horizontal', 'vertical'])('captured %s drag continues off-track until release', axis => {
  const vertical = axis === 'vertical'
  const position = vertical ? 'scrollTop' : 'scrollLeft'
  const disconnect = vi.fn()
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect })
  const wrapper = document.createElement('div'), handle = document.createElement('div')
  wrapper.append(handle); document.body.append(wrapper)
  Object.defineProperties(handle, { clientWidth: { value: 200 }, scrollWidth: { value: 1000 },
    clientHeight: { value: 200 }, scrollHeight: { value: 1000 } })
  const end = vi.fn()
  const cleanup = (vertical ? installVerticalScrollbar : installHorizontalScrollbar)(handle, { onEnd: end })
  const track = wrapper.querySelector(`.st-${axis}-track`), thumb = track.firstElementChild
  track.setPointerCapture = vi.fn()
  track.hasPointerCapture = () => true
  track.releasePointerCapture = vi.fn()
  const bounds = vi.spyOn(track, 'getBoundingClientRect')
  function pointer(target, type, x, y) {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0,
      clientX: vertical ? y : x, clientY: vertical ? x : y })
    Object.defineProperty(event, 'pointerId', { value: 7 })
    target.dispatchEvent(event)
  }
  try {
    pointer(thumb, 'pointerdown', 10, 500)
    expect(track.setPointerCapture).toHaveBeenCalledWith(7)
    pointer(track, 'pointermove', 50, 250)
    expect(handle[position]).toBe(200)
    pointer(track, 'pointermove', 90, -100)
    expect(handle[position]).toBe(400)
    expect(bounds).not.toHaveBeenCalled()
    pointer(track, 'pointerup', 90, -100)
    expect(track.releasePointerCapture).toHaveBeenCalledWith(7)
    expect(end).toHaveBeenCalledTimes(1)
    pointer(track, 'pointermove', 130, -100)
    expect(handle[position]).toBe(400)
    handle[position] = 600
    handle.dispatchEvent(new Event('scroll'))
    expect(track.getAttribute('aria-valuenow')).toBe('600')
  } finally { cleanup(); wrapper.remove(); vi.unstubAllGlobals() }
  expect(disconnect).toHaveBeenCalledTimes(1)
  expect(handle.style.opacity).toBe('')
})
