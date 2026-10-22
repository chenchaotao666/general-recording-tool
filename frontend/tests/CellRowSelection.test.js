// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'
import { expect, test, vi } from 'vitest'
import { useCellRange } from '../src/smart/utils/useCellRange.js'

test('row numbers select whole rows, Shift extends from a stable anchor in either direction', async () => {
  const scope = effectScope()
  const rows = ref(Array.from({ length: 5 }, (_, i) => ({ id: i + 1, __key: `r_${i + 1}` })))
  const fields = ref([{ field_name: 'a' }, { field_name: 'b' }])
  const selected = ref(null)
  const onRowsSelected = vi.fn()
  const range = scope.run(() => useCellRange({ table: ref(null), rows, fields, selected, editing: ref(null),
    buffer: ref(null), dirs: () => ({}), canEdit: () => true, paste: () => {}, clearColumns: () => {}, onRowsSelected }))
  const selectedRows = () => rows.value.filter(r => range.classes(r, 'a').includes('cell-range')).map(r => r.id)
  range.selectRow(rows.value[2])
  expect(selectedRows()).toEqual([3])
  expect(range.classes(rows.value[2], 'b')).toContain('range-right')
  expect(range.classes(rows.value[2], undefined, true)).toContain('cell-range')
  expect(range.classes(rows.value[2], undefined, true)).toContain('range-left')
  expect(range.classes(rows.value[2], 'a')).not.toContain('range-left')
  await nextTick()
  expect(onRowsSelected.mock.lastCall[0].map(r => r.id)).toEqual([3])
  range.selectRow(rows.value[4], true)
  expect(selectedRows()).toEqual([3, 4, 5])
  expect(range.contextRows(rows.value[3], 'b').map(r => r.id)).toEqual([3, 4, 5])
  expect(range.contextRows(rows.value[3], undefined, true).map(r => r.id)).toEqual([3, 4, 5])
  expect(range.contextRows(rows.value[1], 'b')).toBeNull()
  range.selectRow(rows.value[0], true)
  expect(selectedRows()).toEqual([1, 2, 3])
  range.extend('down')
  expect(selectedRows()).toEqual([2, 3])
  range.selectRow(rows.value[3])
  expect(selectedRows()).toEqual([4])
  await nextTick()
  expect(onRowsSelected.mock.lastCall[0].map(r => r.id)).toEqual([4])
  selected.value = { key: 'r_1', fieldName: 'b' }
  expect(range.multiple.value).toBe(false)
  await nextTick()
  expect(onRowsSelected.mock.lastCall[0]).toEqual([])
  scope.stop()
})
