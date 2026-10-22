import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CLIPBOARD_TYPE, TYPE_MESSAGE, copyCell, planPaste, rangeBounds, readClipboard, toTSV } from './cellClipboard.js'
import { nextCell } from './cellNavigation.js'
import { planFill } from './cellFill.js'

export function useCellRange({ table, rows, fields, selected, editing, buffer, dirs, canEdit, paste, clearColumns, onRowsSelected = () => {} }) {
  const end = ref(null)
  const rowAnchor = ref(null)
  const fillPreview = ref(null)
  const wholeRow = computed(() => rowAnchor.value != null)
  const dataRows = computed(() => rows.value.filter(r => !r.__rowType))
  const bounds = computed(() => rangeBounds(dataRows.value, fields.value, selected.value, end.value || selected.value))
  const multiple = computed(() => !!bounds.value && (!!fillPreview.value || rowAnchor.value != null || bounds.value.top !== bounds.value.bottom || bounds.value.left !== bounds.value.right))
  const clearRange = () => { end.value = null; rowAnchor.value = null }
  watch(selected, clearRange, { flush: 'sync' })
  watch(editing, value => { if (value) clearRange() }, { flush: 'sync' })
  const wholeRows = computed(() => rowAnchor.value != null && bounds.value
    ? dataRows.value.slice(bounds.value.top, bounds.value.bottom + 1) : null)
  watch(wholeRows, (value, old) => {
    if (value || old) onRowsSelected(value || [])
  })
  let drag = null, suppressClick = false, pending = false
  let scrollFrame = 0
  function stopScroll() { cancelAnimationFrame(scrollFrame); scrollFrame = 0 }
  const focus = () => nextTick(() => buffer.value?.focus({ preventScroll: true }))
  function cellAt(target) {
    const td = target?.closest?.('td.vxe-body--column')
    if (!td || !table.value?.$el.contains(td)) return null
    const row = table.value.getRowNode(td.closest('tr'))?.item
    const column = table.value.getColumnNode(td)?.item
    if (!row || row.__rowType || !fields.value.length) return null
    if (column?.params?.rowNumber) return { key: row.__key, fieldName: fields.value[0].field_name, rowNumber: true }
    return fields.value.some(f => f.field_name === column?.field) ? { key: row.__key, fieldName: column.field } : null
  }
  function down(e) {
    suppressClick = false
    stopScroll(); drag = null
    const b = bounds.value
    const td = e.target.closest?.('td.cell-fill-handle')
    const rect = td?.getBoundingClientRect()
    if (e.button === 0 && rect && b && !pending && !editing.value
      && e.clientX >= rect.right - 9 && e.clientY >= rect.bottom - 9) {
      e.preventDefault(); e.stopPropagation()
      const cell = { key: dataRows.value[b.bottom].__key, fieldName: fields.value[b.right].field_name }
      drag = { cell, x: e.clientX, y: e.clientY, pointerX: e.clientX, pointerY: e.clientY,
        moved: false, source: { ...b }, target: b.bottom,
        matrix: dataRows.value.slice(b.top, b.bottom + 1).map(row => fields.value.slice(b.left, b.right + 1)
          .map(field => copyCell(field, row[field.field_name], dirs()))) }
      suppressClick = true
      return
    }
    if (e.button !== 0 || e.target.closest('input, textarea, button, .cell-dropdown, .tag-remove, .remove-btn')) return
    const cell = cellAt(e.target)
    if (!cell) return
    if (!cell.rowNumber && e.shiftKey && selected.value && !editing.value) {
      e.preventDefault(); e.stopPropagation()
      end.value = cell; suppressClick = true; drag = null; focus()
      return
    }
    if (editing.value && !cell.rowNumber) return
    drag = { cell, x: e.clientX, y: e.clientY, pointerX: e.clientX, pointerY: e.clientY, shift: e.shiftKey, moved: false }
  }
  function viewport() {
    return table.value?.$el?.querySelector('.body--wrapper > .vxe-table--body-inner-wrapper')
  }
  function updateDrag() {
    if (!drag) return
    const body = viewport(), rect = body?.getBoundingClientRect()
    const x = Math.max(1, Math.min(window.innerWidth - 2, drag.pointerX))
    const y = rect ? Math.max(Math.max(1, rect.top + 2), Math.min(Math.min(window.innerHeight - 2, rect.bottom - 2), drag.pointerY)) : drag.pointerY
    const cell = cellAt(document.elementFromPoint(x, y))
    if (drag.source) {
      if (!cell) return
      drag.target = dataRows.value.findIndex(row => row.__key === cell.key)
      drag.moved = true
      fillPreview.value = { ...drag.source, top: Math.min(drag.source.top, drag.target), bottom: Math.max(drag.source.bottom, drag.target) }
      window.getSelection()?.removeAllRanges()
      return
    }
    if (!cell || (cell.key === drag.cell.key && cell.fieldName === drag.cell.fieldName && !drag.moved)) return
    if (!drag.moved) {
      drag.moved = true
      if (drag.cell.rowNumber) selectRow(dataRows.value.find(r => r.__key === drag.cell.key), drag.shift)
      else { editing.value = null; clearColumns(); selected.value = drag.cell }
      window.getSelection()?.removeAllRanges()
    }
    const fieldName = drag.cell.rowNumber ? fields.value.at(-1).field_name : cell.fieldName
    if (end.value?.key !== cell.key || end.value?.fieldName !== fieldName) end.value = { key: cell.key, fieldName }
  }
  function autoScroll() {
    scrollFrame = 0
    if (!drag) return
    const body = viewport()
    if (body) {
      const rect = body.getBoundingClientRect()
      const top = Math.max(0, rect.top), bottom = Math.min(window.innerHeight, rect.bottom)
      const distance = drag.pointerY < top + 28 ? drag.pointerY - top - 28
        : drag.pointerY > bottom - 28 ? drag.pointerY - bottom + 28 : 0
      if (distance && drag.pointerX >= rect.left - 40 && drag.pointerX <= rect.right + 40) {
        const step = Math.sign(distance) * Math.min(24, Math.max(4, Math.abs(distance) / 3))
        const next = Math.max(0, Math.min(body.scrollHeight - body.clientHeight, body.scrollTop + step))
        if (next !== body.scrollTop) table.value?.scrollTo?.(undefined, next)
      }
    }
    updateDrag()
    scrollFrame = requestAnimationFrame(autoScroll)
  }
  function move(e) {
    if (!drag) return
    if (!e.buttons) { cancel(); return }
    if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < 5 && !drag.moved) return
    e.preventDefault()
    drag.pointerX = e.clientX; drag.pointerY = e.clientY
    updateDrag()
    if (!scrollFrame) scrollFrame = requestAnimationFrame(autoScroll)
  }
  function up() {
    stopScroll()
    const fill = drag?.source ? drag : null
    if (drag?.moved) { suppressClick = true; focus() }
    drag = null
    if (fill?.moved) finishFill(fill)
    fillPreview.value = null
  }
  function cancel() {
    stopScroll(); drag = null; fillPreview.value = null
  }
  function keydown(e) {
    if (e.key === 'Escape' && drag?.source) { e.preventDefault(); cancel() }
    if (!['Backspace', 'Delete'].includes(e.key) || !owns(e) || !bounds.value
      || e.isComposing || e.keyCode === 229 || e.ctrlKey || e.metaKey || e.altKey) return
    e.preventDefault(); e.stopPropagation()
    if (!pending && !drag) clearContents()
  }
  async function clearContents() {
    try {
      const { changes, skipped } = planPaste([[{ type: 'text', text: '', value: null }]],
        dataRows.value, fields.value, bounds.value, canEdit)
      if (!changes.length) { ElMessage.info(skipped[0]?.reason || '没有可清空的单元格'); return }
      pending = true
      const result = await paste(changes)
      const rejected = [...skipped, ...(result?.skipped || [])]
      const count = result?.applied?.length ?? changes.length
      if (rejected.length) ElMessage.info(count
        ? `已清空 ${count} 个单元格，跳过 ${rejected.length} 个无法编辑的单元格`
        : rejected[0].reason || '没有可清空的单元格')
    } catch (error) { ElMessage.info(error.message || '清空失败') }
    finally { pending = false; focus() }
  }
  async function finishFill(fill) {
    if (pending || fill.target >= fill.source.top && fill.target <= fill.source.bottom) return
    // 松手时直接将预览范围转为选区，不等待保存响应，避免选框先缩回再展开。
    selected.value = { key: dataRows.value[Math.min(fill.source.top, fill.target)].__key, fieldName: fields.value[fill.source.left].field_name }
    end.value = { key: dataRows.value[Math.max(fill.source.bottom, fill.target)].__key, fieldName: fields.value[fill.source.right].field_name }
    try {
      const { changes, skipped } = planFill(fill.matrix, dataRows.value, fields.value, fill.source, fill.target, canEdit)
      if (!changes.length) { ElMessage.info(skipped[0]?.reason || '没有可填充的单元格'); return }
      pending = true
      const result = await paste(changes)
      const rejected = [...skipped, ...(result?.skipped || [])]
      const count = result?.applied?.length ?? changes.length
      if (rejected.length) ElMessage.info(count ? `已填充 ${count} 个单元格，跳过 ${rejected.length} 个无法填充的单元格` : rejected[0].reason)
    } catch (error) { ElMessage.info(error.message || '填充失败') }
    finally { pending = false; focus() }
  }
  function click(e) {
    if (suppressClick) {
      suppressClick = false; e.preventDefault(); e.stopPropagation(); focus()
    } else if (multiple.value && cellAt(e.target) && !cellAt(e.target).rowNumber) {
      // Even a click on the active corner collapses the rectangle.
      clearRange()
    }
  }
  function selectRow(row, shift = false) {
    if (row.__rowType || !fields.value.length) return
    const anchor = shift ? rowAnchor.value || selected.value?.key || row.__key : row.__key
    document.activeElement?.blur?.()
    editing.value = null
    clearColumns()
    selected.value = { key: anchor, fieldName: fields.value[0].field_name }
    rowAnchor.value = anchor
    end.value = { key: row.__key, fieldName: fields.value.at(-1).field_name }
    focus()
  }
  function extend(direction) {
    const target = nextCell(dataRows.value, fields.value, end.value || selected.value, direction)
    if (target) {
      if (rowAnchor.value != null && ['up', 'down'].includes(direction)) {
        selectRow(dataRows.value.find(r => r.__key === target.key), true)
        table.value?.scrollToRow?.(dataRows.value.find(r => r.__key === target.key))
        return
      }
      rowAnchor.value = null
      end.value = target
      table.value?.scrollToRow?.(dataRows.value.find(r => r.__key === target.key))
      table.value?.scrollToColumn?.(table.value?.getColumnByField?.(target.fieldName))
    }
  }
  function classes(row, name, rowNumber = false) {
    const b = fillPreview.value || bounds.value
    if (!b) return []
    const r = dataRows.value.findIndex(x => x.__key === row.__key), c = fields.value.findIndex(f => f.field_name === name)
    const handle = !rowNumber && !wholeRow.value && !editing.value && r === b.bottom && c === b.right
      && fields.value[c] && canEdit(row, fields.value[c]) ? ['cell-fill-handle'] : []
    if (!multiple.value && !fillPreview.value) return handle
    if (rowNumber && rowAnchor.value != null && r >= b.top && r <= b.bottom) {
      return ['cell-range', 'range-left', r === b.top && 'range-top', r === b.bottom && 'range-bottom'].filter(Boolean)
    }
    if (r < b.top || r > b.bottom || c < b.left || c > b.right) return []
    return [...handle, 'cell-range', r === b.top && 'range-top', r === b.bottom && 'range-bottom', rowAnchor.value == null && c === b.left && 'range-left', c === b.right && 'range-right',
      rowAnchor.value == null && selected.value?.key === row.__key && selected.value?.fieldName === name && 'range-anchor'].filter(Boolean)
  }
  const owns = e => e.target === buffer.value && selected.value && !editing.value
  function contextRows(row, fieldName, rowNumber = false) {
    const b = bounds.value
    if (!multiple.value || !b) return null
    const r = dataRows.value.findIndex(item => item.__key === row.__key)
    const c = fields.value.findIndex(field => field.field_name === fieldName)
    if (r < b.top || r > b.bottom || !(rowNumber && rowAnchor.value != null) && (c < b.left || c > b.right)) return null
    return dataRows.value.slice(b.top, b.bottom + 1)
  }
  function copy(e) {
    if (!owns(e) || !bounds.value || !e.clipboardData) return
    const b = bounds.value
    const cells = dataRows.value.slice(b.top, b.bottom + 1).map(row => fields.value.slice(b.left, b.right + 1).map(field => copyCell(field, row[field.field_name], dirs())))
    e.preventDefault()
    e.clipboardData.setData('text/plain', toTSV(cells))
    e.clipboardData.setData(CLIPBOARD_TYPE, JSON.stringify({ version: 1, cells }))
    ElMessage.success(`已复制${cells.length * cells[0].length}个单元格`)
  }
  async function onPaste(e) {
    if (!owns(e) || !bounds.value || !e.clipboardData) return
    e.preventDefault()
    if (pending) return
    try {
      if (!Array.from(e.clipboardData.types).includes('text/plain')) throw new Error(TYPE_MESSAGE)
      const { changes, skipped } = planPaste(readClipboard(e.clipboardData), dataRows.value, fields.value, bounds.value, canEdit)
      if (!changes.length) { ElMessage.info(skipped[0]?.reason || '没有可粘贴的单元格'); return }
      pending = true
      const result = await paste(changes)
      const rejected = [...skipped, ...(result?.skipped || [])]
      const count = result?.applied?.length ?? changes.length
      if (rejected.length) ElMessage.info(count
        ? `已粘贴 ${count} 个单元格，跳过 ${rejected.length} 个无法粘贴的单元格`
        : rejected[0].reason || '没有可粘贴的单元格')
    } catch (error) { ElMessage.info(error.message || '粘贴失败') }
    finally { pending = false; focus() }
  }
  function attach() {
    window.addEventListener('blur', cancel)
    document.addEventListener('keydown', keydown)
    document.addEventListener('pointermove', move, { passive: false })
    document.addEventListener('pointerup', up)
    document.addEventListener('pointercancel', cancel)
    document.addEventListener('copy', copy)
    document.addEventListener('paste', onPaste)
  }
  function detach() {
    stopScroll()
    window.removeEventListener('blur', cancel)
    document.removeEventListener('keydown', keydown)
    fillPreview.value = null
    drag = null; suppressClick = false
    document.removeEventListener('pointermove', move)
    document.removeEventListener('pointerup', up)
    document.removeEventListener('pointercancel', cancel)
    document.removeEventListener('copy', copy)
    document.removeEventListener('paste', onPaste)
  }
  return { multiple, wholeRow, classes, down, click, extend, selectRow, contextRows, attach, detach }
}
