// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'
import { expect, test, vi } from 'vitest'
import { useCellRange } from '../src/smart/utils/useCellRange.js'

test.each(['Backspace', 'Delete'])('%s clears editable contents across selected rows and preserves selection', async key => {
  const scope = effectScope()
  const rows = ref([{ id: 1, __key: 'r_1', a: 'one' }, { id: 2, __key: 'r_2', a: 'two' }])
  const fields = ref([{ field_name: 'a', field_type: 'text' }, { field_name: 'b', field_type: 'number' },
    { field_name: 'c', field_type: 'formula' }])
  const selected = ref(null), editing = ref(null)
  const buffer = ref(document.createElement('textarea'))
  document.body.append(buffer.value)
  const paste = vi.fn(async changes => ({ applied: changes }))
  const range = scope.run(() => useCellRange({ table: ref(null), rows, fields, selected, editing,
    buffer, dirs: () => ({}), canEdit: (row, field) => !(row.id === 2 && field.field_name === 'b'),
    paste, clearColumns: () => {} }))
  try {
    range.attach()
    range.selectRow(rows.value[0])
    range.selectRow(rows.value[1], true)
    await nextTick()
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
    buffer.value.dispatchEvent(event)
    await nextTick()
    expect(event.defaultPrevented).toBe(true)
    expect(paste.mock.calls[0][0].map(c => [c.row.id, c.field.field_name, c.value])).toEqual([[1, 'a', ''], [1, 'b', null], [2, 'a', '']])
    expect(range.contextRows(rows.value[0], 'a')).toHaveLength(2)
    expect(rows.value).toHaveLength(2)
    editing.value = { key: 'r_1', fieldName: 'a' }
    buffer.value.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
    expect(paste).toHaveBeenCalledOnce()
  } finally { range.detach(); scope.stop(); buffer.value.remove() }
})
