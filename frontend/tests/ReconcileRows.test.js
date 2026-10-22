import { expect, test } from 'vitest'
import { computed, nextTick, ref, watchEffect } from 'vue'
import { mergeUpdatedRows, reconcileRows } from '../src/smart/utils/reconcileRows.js'

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

test('batch paste immediately invalidates cached display rows without mutating old snapshots', async () => {
  const rows = ref([{ id: 1, text: 'before' }, { id: 2, text: 'unchanged' }])
  const display = computed(previous => reconcileRows(previous || [],
    rows.value.map(row => ({ ...row, __key: `r_${row.id}` })), row => row.__key))
  const before = display.value
  let rendered
  const stop = watchEffect(() => { rendered = display.value.map(row => row.text).join(',') })
  rows.value = mergeUpdatedRows(rows.value, [{ id: 1, text: 'after' }])
  await nextTick()
  expect(rendered).toBe('after,unchanged')
  expect(display.value[0]).not.toBe(before[0])
  expect(display.value[1]).toBe(before[1])
  expect(before[0].text).toBe('before')
  expect(display.value[0].__key).toBe('r_1')
  stop()
})
