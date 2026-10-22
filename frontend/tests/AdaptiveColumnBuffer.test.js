import { afterEach, expect, test, vi } from 'vitest'
import { applyColumnBuffer, createAdaptiveColumnBuffer, WIDE_COLUMN_BUFFER } from '../src/smart/utils/adaptiveColumnBuffer.js'

function table() {
  const columns = Array.from({ length: 100 }, (_, id) => ({ id, renderWidth: 100, fixed: id === 0 ? 'left' : null }))
  return {
    internalData: { visibleColumn: columns, fullColumnIdData: Object.fromEntries(columns.map(c => [c.id, { oLeft: c.id * 100 }])),
      scrollXStore: { preloadSize: 20, offsetSize: 20, startIndex: 0, endIndex: 70, visibleSize: 10 } },
    reactData: { scrollXLoad: true }, getScroll: () => ({ scrollLeft: 2000, scrollTop: 100 }), updateScrollXData: vi.fn(),
  }
}
afterEach(() => vi.useRealTimers())

test('shrinks only the virtual columns using cached offsets and preserves the scroll position', () => {
  const t = table(), config = vi.fn()
  expect(applyColumnBuffer(t, 3, config)).toBe(true)
  expect(t.internalData.scrollXStore).toMatchObject({ startIndex: 13, endIndex: 36, preloadSize: 3, offsetSize: 3 })
  expect(t.getScroll()).toEqual({ scrollLeft: 2000, scrollTop: 100 })
  expect(t.updateScrollXData).toHaveBeenCalledTimes(1)
  expect(applyColumnBuffer(t, 20, config)).toBe(true)
  expect(t.internalData.scrollXStore).toMatchObject({ startIndex: 0, endIndex: 70, preloadSize: 20 })
})

test('short scrolls stay wide; sustained scrolling shrinks once and idle restores once', () => {
  vi.useFakeTimers()
  vi.setSystemTime(0)
  const t = table(), config = vi.fn()
  const buffer = createAdaptiveColumnBuffer({ getTable: () => t, setConfig: config, now: () => Date.now() })
  const tick = ms => vi.advanceTimersByTime(ms)
  buffer.vertical(); tick(100); buffer.vertical()
  expect(config).not.toHaveBeenCalled()
  tick(100); buffer.vertical()
  expect(t.internalData.scrollXStore.preloadSize).toBe(3)
  tick(100); buffer.vertical(); tick(100); buffer.vertical()
  expect(t.updateScrollXData).toHaveBeenCalledTimes(1)
  tick(600)
  expect(t.internalData.scrollXStore.preloadSize).toBe(3)
  buffer.vertical() // A pause between wheel gestures must not expand/rebuild.
  expect(t.updateScrollXData).toHaveBeenCalledTimes(1)
  tick(1499)
  expect(t.internalData.scrollXStore.preloadSize).toBe(3)
  tick(1)
  expect(t.internalData.scrollXStore.preloadSize).toBe(WIDE_COLUMN_BUFFER)
  expect(t.updateScrollXData).toHaveBeenCalledTimes(2)
  buffer.dispose()
})

test('horizontal input restores immediately and disposal cancels delayed work', () => {
  vi.useFakeTimers()
  let time = 0
  const t = table()
  const buffer = createAdaptiveColumnBuffer({ getTable: () => t, setConfig: vi.fn(), now: () => time })
  buffer.vertical(); time = 100; buffer.vertical(); time = 200; buffer.vertical()
  buffer.horizontal()
  expect(t.internalData.scrollXStore.preloadSize).toBe(WIDE_COLUMN_BUFFER)
  time = 300; buffer.vertical(); time = 400; buffer.vertical()
  expect(t.updateScrollXData).toHaveBeenCalledTimes(2)
  buffer.dispose(); vi.runAllTimers()
  expect(t.updateScrollXData).toHaveBeenCalledTimes(2)
})

test('unsupported and merged layouts keep the wide fallback', () => {
  const t = table(), config = vi.fn()
  t.internalData.mergeBodyList = [{ col: 0, colspan: 30 }]
  expect(applyColumnBuffer(t, 3, config)).toBe(false)
  expect(applyColumnBuffer(null, 3, config)).toBe(false)
  expect(config).not.toHaveBeenCalled()
})

test('a captured slow drag stays narrow until released instead of repeatedly expanding', () => {
  vi.useFakeTimers()
  let time = 0
  const t = table()
  const buffer = createAdaptiveColumnBuffer({ getTable: () => t, setConfig: vi.fn(), now: () => time })
  buffer.beginVerticalDrag()
  for (let i = 0; i < 3; i++) { buffer.vertical(); time += 350; vi.advanceTimersByTime(350) }
  expect(t.internalData.scrollXStore.preloadSize).toBe(3)
  time += 1000; vi.advanceTimersByTime(1000)
  expect(t.internalData.scrollXStore.preloadSize).toBe(3)
  buffer.endVerticalDrag()
  time += 300; vi.advanceTimersByTime(300)
  expect(t.internalData.scrollXStore.preloadSize).toBe(WIDE_COLUMN_BUFFER)
  buffer.dispose()
})
