import { expect, test } from 'vitest'
import { fitTagRows } from '../src/smart/utils/tagRows.js'

test('wraps tags into all available complete rows and only counts the remaining items', () => {
  expect(fitTagRows([45, 45, 45], 100, 52).map(row => row.map(item => item.index))).toEqual([[0, 1], [2]])
  const rows = fitTagRows([45, 45, 45, 45, 45], 100, 52)
  expect(rows.map(row => row.map(item => item.index))).toEqual([[0, 1], [2, 3]])
  expect(rows[1].reduce((sum, item) => sum + item.width, 0) + 8 + 28).toBeLessThanOrEqual(100)
})

test('files stack into complete rows, reserving a badge beside the final filename', () => {
  const rows = fitTagRows([140, 80, 200, 100], 160, 80, { stacked: true })
  expect(rows.map(row => row.map(item => item.index))).toEqual([[0], [1], [2]])
  expect(rows[2][0].width).toBe(128)
})

test('default height shows one row; increased height and width expose more items', () => {
  expect(fitTagRows([70, 70, 70], 100, 24).flat()).toHaveLength(1)
  expect(fitTagRows([70, 70, 70], 100, 80).flat()).toHaveLength(3)
  expect(fitTagRows([70, 70, 70], 220, 24).flat()).toHaveLength(3)
  expect(fitTagRows([], 100, 80)).toEqual([])
})
