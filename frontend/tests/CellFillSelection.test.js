// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'
import { expect, test, vi } from 'vitest'
import { useCellRange } from '../src/smart/utils/useCellRange.js'

test('fill preview becomes a persistent selection before the save response', async () => {
  const scope = effectScope()
  const rows = ref(Array.from({ length: 4 }, (_, i) => ({ id: i + 1, __key: `r_${i + 1}`, p: 43 })))
  const fields = ref([{ field_name: 'p', field_type: 'percent' }])
  const selected = ref({ key: 'r_1', fieldName: 'p' })
  const root = document.createElement('table')
  root.innerHTML = '<tbody>' + rows.value.map(r => `<tr data-key="${r.__key}"><td class="vxe-body--column cell-fill-handle"></td></tr>`).join('') + '</tbody>'
  document.body.append(root)
  const cells = root.querySelectorAll('td')
  cells[0].getBoundingClientRect = () => ({ left: 0, top: 0, right: 100, bottom: 36 })
  const previous = document.elementFromPoint
  document.elementFromPoint = () => cells[3]
  let resolveSave
  const paste = vi.fn(() => new Promise(resolve => { resolveSave = resolve }))
  const range = scope.run(() => useCellRange({
    table: ref({ $el: root, getRowNode: tr => ({ item: rows.value.find(r => r.__key === tr.dataset.key) }), getColumnNode: () => ({ item: { field: 'p' } }) }),
    rows, fields, selected, editing: ref(null), buffer: ref(null), dirs: () => ({}),
    canEdit: () => true, paste, clearColumns: () => {},
  }))
  try {
    range.attach()
    range.down({ button: 0, target: cells[0], clientX: 97, clientY: 33, preventDefault() {}, stopPropagation() {} })
    document.dispatchEvent(new MouseEvent('pointermove', { buttons: 1, clientX: 50, clientY: 125 }))
    const selection = () => rows.value.filter(r => range.classes(r, 'p').includes('cell-range')).map(r => r.id)
    expect(selection()).toEqual([1, 2, 3, 4])
    document.dispatchEvent(new MouseEvent('pointerup'))
    await nextTick()
    expect(paste).toHaveBeenCalledOnce()
    expect(selection()).toEqual([1, 2, 3, 4])
    resolveSave({ applied: [1, 2, 3] })
    await Promise.resolve()
    await nextTick()
    expect(selection()).toEqual([1, 2, 3, 4])
  } finally {
    range.detach(); scope.stop(); root.remove()
    document.elementFromPoint = previous
  }
})
