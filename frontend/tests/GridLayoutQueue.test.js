import { afterEach, expect, test, vi } from 'vitest'
import { createGridLayoutQueue } from '../src/smart/utils/gridLayoutQueue.js'

afterEach(() => vi.unstubAllGlobals())

function frames() {
  let id = 0
  const callbacks = new Map()
  vi.stubGlobal('requestAnimationFrame', vi.fn(fn => { callbacks.set(++id, fn); return id }))
  vi.stubGlobal('cancelAnimationFrame', vi.fn(id => callbacks.delete(id)))
  return () => { const jobs = [...callbacks.values()]; callbacks.clear(); jobs.forEach(fn => fn()) }
}

test('dragging cancels scheduled measurements and coalesces changes until resume', () => {
  const flush = frames(), queue = createGridLayoutQueue(), measure = vi.fn()
  queue.enqueue(measure)
  queue.pause()
  for (let i = 0; i < 100; i++) queue.enqueue(measure)
  flush()
  expect(measure).not.toHaveBeenCalled()
  queue.resume()
  flush()
  expect(measure).toHaveBeenCalledTimes(1)
  flush()
  expect(measure).toHaveBeenCalledTimes(1)
})

test('unmounted cells and disposed grids do not measure when scrolling ends', () => {
  const flush = frames(), queue = createGridLayoutQueue(), removed = vi.fn(), kept = vi.fn()
  queue.pause()
  queue.enqueue(removed)
  queue.enqueue(kept)
  queue.cancel(removed)
  queue.resume()
  flush()
  expect(removed).not.toHaveBeenCalled()
  expect(kept).toHaveBeenCalledTimes(1)
  queue.enqueue(kept)
  queue.dispose()
  flush()
  expect(kept).toHaveBeenCalledTimes(1)
})

test('cells share one observer and ignore height-only resize notifications', () => {
  frames()
  let notify
  const observe = vi.fn(), unobserve = vi.fn(), disconnect = vi.fn()
  const Observer = vi.fn(function (callback) {
    notify = callback
    Object.assign(this, { observe, unobserve, disconnect })
  })
  vi.stubGlobal('ResizeObserver', Observer)
  const queue = createGridLayoutQueue(), first = {}, second = {}, changed = vi.fn()
  const stopFirst = queue.observeWidth(first, changed)
  const stopSecond = queue.observeWidth(second, changed)
  expect(Observer).toHaveBeenCalledTimes(1)
  notify([{ target: first, contentRect: { width: 100, height: 20 } }])
  notify([{ target: first, contentRect: { width: 100, height: 36 } }])
  expect(changed).toHaveBeenCalledTimes(1)
  notify([{ target: first, contentRect: { width: 150, height: 36 } }])
  expect(changed).toHaveBeenCalledTimes(2)
  stopFirst()
  expect(unobserve).toHaveBeenCalledWith(first)
  expect(disconnect).not.toHaveBeenCalled()
  stopSecond()
  expect(disconnect).toHaveBeenCalledTimes(1)
})
