import { describe, expect, it } from 'vitest'
import { copyCell, convertCell, displayCell, fromTSV, toTSV, planPaste, rangeBounds, READONLY_MESSAGE, TYPE_MESSAGE } from '../src/smart/utils/cellClipboard.js'

const field = (field_type, options = {}) => ({ field_type, field_name: field_type, options })
describe('cell range clipboard', () => {
  it('copies labels, formatted numbers and complete values, never directory IDs', () => {
    const dirs = { members: new Map([[3, { name: '张三' }]]), relations: new Map([[7, new Map([[9, '需求标题']])]]) }
    expect(displayCell(field('member'), [3], dirs)).toBe('张三')
    expect(displayCell(field('relation', { targetTableId: 7 }), [9], dirs)).toBe('需求标题')
    expect(displayCell(field('image'), ['deadbeef'], dirs)).toBe('图片')
    const f = field('multiSelect', { options: [{ id: 'a', label: '生产' }, { id: 'b', label: '停产' }] })
    const source = copyCell(f, ['a', 'b'])
    expect(convertCell(source, field('text'))).toEqual({ value: '生产、停产' })
    expect(convertCell(source, field('multiSelect'))).toEqual({ labels: ['生产', '停产'] })
    expect(convertCell(source, field('singleSelect'))).toEqual({ labels: ['生产', '停产'] })
    expect(displayCell(field('progress', { numberFormat: 'percent', precision: 'default' }), 12.5)).toBe('12.5%')
  })
  it('roundtrips TSV with multiline cells, quotes and empty trailing columns', () => {
    const values = [['a\tb', 'a"b', ''], ['line\nbreak', '', '末尾']]
    expect(fromTSV(toTSV(values)).map(r => r.map(c => c.text))).toEqual(values)
    expect(fromTSV('a\tb\r\nc\td\r\n').length).toBe(2)
  })
  it('converts text to new enum labels and validates incompatible values', () => {
    const text = value => ({ type: 'text', text: value, value })
    expect(convertCell(text('新选项'), field('singleSelect'))).toEqual({ labels: ['新选项'] })
    expect(convertCell(text('生产、停产'), field('multiSelect'))).toEqual({ labels: ['生产', '停产'] })
    expect(convertCell(text('23.5%'), field('percent'))).toEqual({ value: 23.5 })
    expect(() => convertCell(text('abc'), field('number'))).toThrow(TYPE_MESSAGE)
    expect(() => convertCell(text('张三'), field('member'))).toThrow(TYPE_MESSAGE)
    expect(() => convertCell(text('2026-02-31'), field('date'))).toThrow(TYPE_MESSAGE)
    expect(() => convertCell(text('a'), field('formula'))).toThrow(READONLY_MESSAGE)
    expect(() => convertCell({ type: 'relation', text: '需求', value: [1], targetTableId: 2 }, field('relation', { targetTableId: 3 }))).toThrow(TYPE_MESSAGE)
  })
  it('uses rectangular bounds in both drag directions and repeats scalar paste', () => {
    const rows = [{ __key: 'a' }, { __key: 'b' }], fields = [field('text'), field('multiSelect')]
    const bounds = rangeBounds(rows, fields, { key: 'b', fieldName: 'multiSelect' }, { key: 'a', fieldName: 'text' })
    expect(bounds).toEqual({ top: 0, bottom: 1, left: 0, right: 1 })
    const { changes } = planPaste(fromTSV('新值'), rows, fields, bounds)
    expect(changes).toHaveLength(4)
    expect(changes[1].labels).toEqual(['新值'])
    expect(planPaste(fromTSV('a\tb\tc'), rows, fields, bounds).skipped).toHaveLength(1)
    const readonly = planPaste(fromTSV('a'), rows, [field('text'), field('lookup')], bounds)
    expect(readonly.changes).toHaveLength(2)
    expect(readonly.skipped.map(c => c.reason)).toEqual([READONLY_MESSAGE, READONLY_MESSAGE])
    expect(planPaste(fromTSV('a'), rows, fields, bounds, () => false).changes).toHaveLength(0)
  })
  it('skips incompatible destinations without shifting the remaining matrix', () => {
    const rows = [{ __key: 'a' }, { __key: 'b' }], fields = [field('number'), field('text'), field('formula')]
    const bounds = { top: 0, bottom: 0, left: 0, right: 0 }
    const result = planPaste(fromTSV('bad\tfirst\treadonly\n42\tsecond\treadonly'), rows, fields, bounds)
    expect(result.changes.map(c => [c.row.__key, c.field.field_name, c.value])).toEqual([
      ['a', 'text', 'first'], ['b', 'number', 42], ['b', 'text', 'second'],
    ])
    expect(result.skipped).toHaveLength(3)
  })
})
