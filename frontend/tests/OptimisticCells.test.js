import { expect, test } from 'vitest'
import { previewCells, rollbackCells } from '../src/smart/utils/optimisticCells.js'

test('renders fill immediately and rolls back only rejected cells', () => {
  const rows = [{ id: 1, p: 1 }, { id: 2, p: 2 }, { id: 3, p: 3 }]
  const field = { field_name: 'p', field_type: 'percent' }
  const preview = previewCells(rows, rows.slice(0, 2).map(row => ({ row, field, value: 43 })))
  expect(preview.rows.map(row => row.p)).toEqual([43, 43, 3])
  expect(preview.rows[2]).toBe(rows[2])
  expect(rows[0].p).toBe(1)
  expect(rollbackCells(preview.rows, preview.snapshots, new Set(['1:p'])).map(row => row.p)).toEqual([43, 2, 3])
  expect(rollbackCells(preview.rows, preview.snapshots)).toEqual(rows)
  expect(rollbackCells([{ id: 1, p: 99 }], preview.snapshots)[0].p).toBe(99)
})

test('previews existing enum labels using IDs and waits for new option IDs', () => {
  const rows = [{ id: 1, p: null }]
  const field = { field_name: 'p', field_type: 'singleSelect', options: { options: [{ id: 'a', label: 'A' }] } }
  expect(previewCells(rows, [{ row: rows[0], field, labels: ['A'] }]).rows[0].p).toBe('a')
  expect(previewCells(rows, [{ row: rows[0], field, labels: ['New'] }]).rows).toBe(rows)
})
