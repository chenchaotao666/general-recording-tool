import { expect, test } from 'vitest'
import { nextCell } from '../src/smart/utils/cellNavigation.js'
const rows = [{ __key: 'a' }, { __key: 'group', __rowType: 'group' }, { __key: 'b' }, { __key: 'add', __rowType: 'add' }]
const fields = [{ field_name: 'second' }, { field_name: 'first' }]
test('navigation follows displayed column order and skips non-record rows', () => {
  expect(nextCell(rows, fields, { key: 'a', fieldName: 'second' }, 'down')).toEqual({ key: 'b', fieldName: 'second' })
  expect(nextCell(rows, fields, { key: 'a', fieldName: 'second' }, 'right')).toEqual({ key: 'a', fieldName: 'first' })
  expect(nextCell(rows, fields, { key: 'b', fieldName: 'first' }, 'up')).toEqual({ key: 'a', fieldName: 'first' })
  expect(nextCell(rows, fields, { key: 'b', fieldName: 'first' }, 'left')).toEqual({ key: 'b', fieldName: 'second' })
})
test('grid edges stay selected and stale selections do not navigate', () => {
  const last = { key: 'b', fieldName: 'first' }
  expect(nextCell(rows, fields, last, 'down')).toEqual(last)
  expect(nextCell(rows, fields, last, 'right')).toEqual(last)
  expect(nextCell(rows, fields, { key: 'gone', fieldName: 'first' }, 'down')).toBeNull()
})
