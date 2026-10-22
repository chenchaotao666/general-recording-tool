import { expect, test } from 'vitest'
import { computed, nextTick, ref, watchEffect } from 'vue'
import { updateGridDisplayRows } from '../src/smart/utils/gridDisplayRows.js'
import { previewCells } from '../src/smart/utils/optimisticCells.js'
import { copyCell } from '../src/smart/utils/cellClipboard.js'
import { planFill } from '../src/smart/utils/cellFill.js'

test('typing 1 and 2 then filling before a server refresh retains both source values', async () => {
  const source = ref(Array.from({ length: 5 }, (_, i) => ({ id: i + 1, __key: `r_${i + 1}`, n: null })))
  const display = computed(previous => updateGridDisplayRows(previous || [], source.value))
  const field = { field_name: 'n', field_type: 'number' }
  let rendered
  const stop = watchEffect(() => { rendered = display.value.map(row => row.n) })
  for (let i = 0; i < 2; i++) {
    source.value = previewCells(source.value, [{ row: display.value[i], field, value: i + 1 }]).rows
    await nextTick()
  }
  const matrix = display.value.slice(0, 2).map(row => [copyCell(field, row.n)])
  const plan = planFill(matrix, display.value, [field], { top: 0, bottom: 1, left: 0, right: 0 }, 4, () => true)
  source.value = previewCells(source.value, plan.changes).rows
  await nextTick()
  expect(rendered).toEqual([1, 2, 3, 4, 5])
  expect(source.value.map(row => row.n)).toEqual([1, 2, 3, 4, 5])
  stop()
})

test('optimistic fill and save response update cells without reloading the row array', async () => {
  const source = ref([{ __key: 'r_1', p: 1 }, { __key: 'r_2', p: 2 }, { __key: 'r_3', p: null }])
  const display = computed(previous => updateGridDisplayRows(previous || [], source.value))
  const original = display.value
  let rendered
  const stop = watchEffect(() => { rendered = display.value.map(row => row.p) })
  source.value = source.value.map(row => row.__key === 'r_3' ? { ...row, p: 3 } : row)
  await nextTick()
  expect(display.value).toBe(original)
  expect(rendered).toEqual([1, 2, 3])
  source.value = source.value.map(row => ({ ...row, updated_by: 1 }))
  await nextTick()
  expect(display.value).toBe(original)
  expect(rendered).toEqual([1, 2, 3])
  stop()
})

test('row insertion, sorting and deletion update array order while retaining existing rows', () => {
  const first = updateGridDisplayRows([], [{ __key: 'a', p: 1 }, { __key: 'b', p: 2 }])
  const next = updateGridDisplayRows(first, [{ __key: 'b', p: 2 }, { __key: 'c', p: 3 }, { __key: 'a' }])
  expect(next.map(row => row.__key)).toEqual(['b', 'c', 'a'])
  expect(next[0]).toBe(first[1])
  expect(next[2]).toBe(first[0])
  expect(next[2]).not.toHaveProperty('p')
  expect(updateGridDisplayRows(next, [{ __key: 'c', p: 3 }])).toEqual([next[1]])
})
