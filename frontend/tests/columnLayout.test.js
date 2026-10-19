import { expect, test } from 'vitest'
import { buildColumnLayout } from '../src/smart/utils/columnLayout.js'

const fields = ['a', 'b', 'c', 'd'].map(field_name => ({ field_name }))
const groups = [{ id: 1, name: 'Group', field_names: ['b', 'd'] }]

test('freezing follows grouped display order and fixes the parent header', () => {
  const layout = buildColumnLayout(fields, groups, 'c')
  expect(layout.map(n => n.isGroup ? n.fields.map(f => f.field_name) : n.field.field_name))
    .toEqual(['a', ['b', 'd'], 'c'])
  expect(layout.every(n => n.fixed === 'left')).toBe(true)
})

test('a group crossing the freeze boundary has two consistent header segments', () => {
  const layout = buildColumnLayout(fields, groups, 'b')
  expect(layout.filter(n => n.isGroup).map(n => [n.fixed, n.fields.map(f => f.field_name)]))
    .toEqual([['left', ['b']], [undefined, ['d']]])
  expect(layout.filter(n => n.isGroup).map(n => n.group.id)).toEqual([1, 1])
  expect(new Set(layout.map(n => n.key)).size).toBe(layout.length)
})

test('clearing or hiding the frozen boundary removes frozen group segments', () => {
  for (const id of [null, 'missing']) {
    const layout = buildColumnLayout(fields, groups, id)
    expect(layout.some(n => n.fixed)).toBe(false)
    expect(layout.filter(n => n.isGroup)).toHaveLength(1)
  }
})
