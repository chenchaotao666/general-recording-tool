import { afterEach, expect, test, vi } from 'vitest'
import { waitForGridIdle } from '../src/smart/utils/waitForGridIdle.js'

afterEach(() => vi.useRealTimers())

test('background snapshots wait until dragging ends', async () => {
  vi.useFakeTimers()
  let busy = true
  const apply = vi.fn()
  const pending = waitForGridIdle(() => busy, () => true).then(valid => { if (valid) apply() })
  await vi.advanceTimersByTimeAsync(360)
  expect(apply).not.toHaveBeenCalled()
  busy = false
  await vi.advanceTimersByTimeAsync(120)
  await pending
  expect(apply).toHaveBeenCalledTimes(1)
})

test('navigation or a newer request cancels a snapshot waiting for idle', async () => {
  vi.useFakeTimers()
  let current = true
  const pending = waitForGridIdle(() => true, () => current)
  current = false
  await vi.advanceTimersByTimeAsync(120)
  expect(await pending).toBe(false)
  expect(vi.getTimerCount()).toBe(0)
})
