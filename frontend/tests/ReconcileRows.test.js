import { expect, test } from 'vitest'
import { reconcileRows } from '../src/smart/utils/reconcileRows.js'

test('unchanged refresh keeps the array and nested record objects', () => {
  const rows = [{ id: 1, tags: ['a'], files: [{ id: 'file', name: 'a' }] }]
  expect(reconcileRows(rows, JSON.parse(JSON.stringify(rows)))).toBe(rows)
})

test('changes replace only affected records and preserve server ordering and deletion', () => {
  const rows = [{ id: 1, text: 'a' }, { id: 2, files: [{ name: 'b' }] }, { id: 3 }]
  const result = reconcileRows(rows, [{ id: 2, files: [{ name: 'changed' }] }, { text: 'a', id: 1 }, { id: 4 }])
  expect(result.map(row => row.id)).toEqual([2, 1, 4])
  expect(result[0]).not.toBe(rows[1])
  expect(result[1]).toBe(rows[0])
  expect(rows[1].files[0].name).toBe('b')
})

test('removed keys and group aggregate changes are not ignored', () => {
  const rows = [{ id: 1, value: null }, { __rowType: 'group', key: 'g', aggs: { amount: 1 } }]
  const result = reconcileRows(rows, [{ id: 1 }, { __rowType: 'group', key: 'g', aggs: { amount: 2 } }])
  expect(result[0]).not.toBe(rows[0])
  expect(result[1]).not.toBe(rows[1])
})

test('display rows keep identity only while row number and indentation stay the same', () => {
  const rows = [{ id: 1, __key: 'r_1', __no: 1, __indent: 0 }]
  const key = row => row.__key
  expect(reconcileRows(rows, [{ ...rows[0] }], key)).toBe(rows)
  expect(reconcileRows(rows, [{ ...rows[0], __no: 2 }], key)[0]).not.toBe(rows[0])
  expect(reconcileRows(rows, [{ ...rows[0], __indent: 1 }], key)[0]).not.toBe(rows[0])
})
