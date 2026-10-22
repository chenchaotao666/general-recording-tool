import { expect, test } from 'vitest'
import { canInsertLocally, insertViewRows } from '../src/smart/utils/insertViewRows.js'

test('inserts returned records next to the anchor without replacing existing rows', () => {
  const rows = [{ id: 1 }, { id: 2 }, { id: 3 }]
  const records = [{ id: 4 }, { id: 5 }]
  const result = insertViewRows(rows, records, 2, 'down')
  expect(result.map(r => r.id)).toEqual([1, 2, 4, 5, 3])
  expect(result[0]).toBe(rows[0])
  expect(result[1]).toBe(rows[1])
  expect(result[4]).toBe(rows[2])
  expect(insertViewRows(rows, records, 2, 'up', 3).map(r => r.id)).toEqual([1, 4, 5])
  expect(rows.map(r => r.id)).toEqual([1, 2, 3])
  expect(insertViewRows(rows, records, 99, 'down')).toBeNull()
})

test('a duplicated parent is inserted after the original subtree', () => {
  const rows = [{ id: 1 }, { id: 2, parent_id: 1 }, { id: 3, parent_id: 2 }, { id: 4 }]
  expect(insertViewRows(rows, [{ id: 5 }], 1, 'down').map(r => r.id)).toEqual([1, 2, 3, 5, 4])
})

test('toolbar add prepends locally, including an empty table', () => {
  const row = { id: 1 }, added = { id: 2 }
  expect(insertViewRows([], [added], null, 'up')).toEqual([added])
  const result = insertViewRows([row], [added], null, 'up')
  expect(result.map(r => r.id)).toEqual([2, 1])
  expect(result[1]).toBe(row)
})

test('views with ordering, filters, groups or scoped permissions use silent synchronization', () => {
  expect(canInsertLocally({}, false, true, 'grid')).toBe(true)
  for (const cfg of [{ sorts: [{}] }, { groups: [{}] }, { filters: { conditions: [{}] } }]) {
    expect(canInsertLocally(cfg, false, true, 'grid')).toBe(false)
  }
  expect(canInsertLocally({}, false, false, 'grid')).toBe(false)
  expect(canInsertLocally({}, true, true, 'grid')).toBe(false)
  expect(canInsertLocally({}, false, true, 'kanban')).toBe(false)
})
