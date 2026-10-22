import { expect, test } from 'vitest'
import { rowHeightPixels, tagRowCapacity, wrappedTextWidth, wrappedTagWidth } from '../src/smart/utils/autoColumnWidth.js'

test('automatic widths share the grid row heights and fit only complete tag rows', () => {
  expect(['default', 'medium', 'tall', 'extraTall'].map(rowHeightPixels)).toEqual([36, 52, 76, 100])
  expect(rowHeightPixels(3)).toBe(80)
  expect([36, 52, 76, 100].map(tagRowCapacity)).toEqual([1, 1, 2, 3])
})

test('text uses additional lines without exceeding the automatic width cap', () => {
  const measure = text => Array.from(text).length * 10
  expect(wrappedTextWidth('abcdefghijkl', 36, measure)).toBe(120)
  expect(wrappedTextWidth('abcdefghijkl', 52, measure)).toBe(60)
  expect(wrappedTextWidth('abcdefghijkl', 76, measure)).toBe(40)
  expect(wrappedTextWidth('x'.repeat(1000), 100, measure)).toBe(276)
  expect(wrappedTextWidth('', 100, measure)).toBe(0)
})

test('multiple tags can narrow as row height grows, but complete long names still set the minimum', () => {
  expect(wrappedTagWidth([60, 60, 60], 36)).toBe(188)
  expect(wrappedTagWidth([60, 60, 60], 76)).toBe(124)
  expect(wrappedTagWidth([60, 60, 60], 100)).toBe(60)
  expect(wrappedTagWidth([150, 20, 20], 100)).toBe(150)
})

test('files measure visible filenames and reserve space for the remaining count', () => {
  expect(wrappedTagWidth([80, 100, 90], 36, { stacked: true })).toBe(112)
  expect(wrappedTagWidth([80, 100, 90], 100, { stacked: true })).toBe(100)
  expect(wrappedTagWidth([80, 100, 90, 250], 100, { stacked: true })).toBe(122)
})
