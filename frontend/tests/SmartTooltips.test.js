// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { installSmartTooltips } from '../src/smart/utils/tooltips.js'

test('file tooltip only appears when its filename is clipped', () => {
  vi.useFakeTimers()
  document.body.innerHTML = '<button data-smart-tip="Report.pdf" data-smart-tip-overflow="span"><span>Report.pdf</span></button>'
  const text = document.querySelector('span')
  let width = 80
  Object.defineProperty(text, 'scrollWidth', { get: () => width })
  Object.defineProperty(text, 'clientWidth', { value: 80 })
  const cleanup = installSmartTooltips()
  try {
    text.dispatchEvent(new Event('pointerover', { bubbles: true }))
    vi.advanceTimersByTime(300)
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    width = 120
    text.dispatchEvent(new Event('pointerover', { bubbles: true }))
    vi.advanceTimersByTime(300)
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe('Report.pdf')
  } finally {
    cleanup(); document.body.innerHTML = ''; vi.useRealTimers()
  }
})
