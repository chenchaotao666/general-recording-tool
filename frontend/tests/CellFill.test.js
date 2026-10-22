import { expect, test } from 'vitest'
import { copyCell } from '../src/smart/utils/cellClipboard.js'
import { planFill } from '../src/smart/utils/cellFill.js'
import { formatNumber } from '../src/smart/utils/format.js'

const fields = [{ field_name: 'p', field_type: 'percent' }]
const rows = Array.from({ length: 9 }, (_, id) => ({ id, __key: `r_${id}` }))
const matrix = values => values.map(value => [copyCell(fields[0], value)])

test('fills down with the same percentage without overwriting source', () => {
  const result = planFill(matrix([43]), rows, fields, { top: 1, bottom: 1, left: 0, right: 0 }, 5, () => true)
  expect(result.changes.map(c => [c.row.id, c.value])).toEqual([[2, 43], [3, 43], [4, 43], [5, 43]])
})

test('extends numeric series up and down', () => {
  const source = { top: 3, bottom: 4, left: 0, right: 0 }
  expect(planFill(matrix([10, 20]), rows, fields, source, 7, () => true).changes.map(c => c.value)).toEqual([30, 40, 50])
  expect(planFill(matrix([10, 20]), rows, fields, source, 0, () => true).changes.map(c => c.value)).toEqual([-20, -10, 0])
  expect(planFill(matrix([10, 20]), rows, fields, source, 3, () => true).changes).toEqual([])
})

test('skips protected destinations without shifting the pattern', () => {
  const result = planFill(matrix([10, 20]), rows, fields, { top: 0, bottom: 1, left: 0, right: 0 }, 4, row => row.id !== 3)
  expect(result.changes.map(c => [c.row.id, c.value])).toEqual([[2, 30], [4, 50]])
  expect(result.skipped).toHaveLength(1)
})

test.each([
  [[1, 2], [3, 4, 5]],
  [[5, 3], [1, -1, -3]],
  [[0.1, 0.2], [0.3, 0.4, 0.5]],
  [[43, 43], [43, 43, 43]],
])('extends %j with a stable numeric step', (values, expected) => {
  expect(planFill(matrix(values), rows, fields, { top: 0, bottom: 1, left: 0, right: 0 }, 4, () => true).changes.map(c => c.value)).toEqual(expected)
})

test('mixed columns extend numbers and repeat text independently', () => {
  const columns = [fields[0], { field_name: 'label', field_type: 'text' }]
  const source = [[copyCell(columns[0], 1), copyCell(columns[1], 'A')], [copyCell(columns[0], 2), copyCell(columns[1], 'B')]]
  expect(planFill(source, rows, columns, { top: 0, bottom: 1, left: 0, right: 1 }, 4, () => true).changes.map(c => c.value)).toEqual([3, 'A', 4, 'B', 5, 'A'])
})

test('2, 4, 5 follows the reference linear trend and column precision', () => {
  const field = { field_name: 'n', field_type: 'number', options: { precision: 2 } }
  const source = [2, 4, 5].map(value => [copyCell(field, value)])
  const result = planFill(source, rows, [field], { top: 0, bottom: 2, left: 0, right: 0 }, 7, () => true)
  expect(result.changes.map(c => formatNumber(c.value, field.options))).toEqual(['6.67', '8.17', '9.67', '11.17', '12.67'])
  expect(result.changes[0].value).toBe(6.67)
  expect(result.changes.map(c => c.row.id)).toEqual([3, 4, 5, 6, 7])
  expect(source.map(row => row[0].value)).toEqual([2, 4, 5])
})

test('default precision avoids long fractions and preserves finer source decimals', () => {
  const field = { field_name: 'n', field_type: 'number', options: {} }
  const source = [2, 4, 5].map(value => [copyCell(field, value)])
  const result = planFill(source, rows, [field], { top: 0, bottom: 2, left: 0, right: 0 }, 7, () => true)
  expect(result.changes.map(c => formatNumber(c.value))).toEqual(['6.67', '8.17', '9.67', '11.17', '12.67'])
  const fine = [0.001, 0.002].map(value => [copyCell(field, value)])
  expect(planFill(fine, rows, [field], { top: 0, bottom: 1, left: 0, right: 0 }, 4, () => true).changes.map(c => c.value)).toEqual([0.003, 0.004, 0.005])
})
