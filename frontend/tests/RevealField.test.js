import { expect, test } from 'vitest'
import { fieldScrollLeft, rowScrollTop } from '../src/smart/utils/revealField.js'
const columns = [{ field: 'number', fixed: 'left', renderWidth: 40 }, ...['a', 'b', 'c', 'd'].map(field => ({ field, renderWidth: 100 }))]
test('reveals only the clipped portion and keeps visible or frozen fields stationary', () => {
  expect(fieldScrollLeft(columns, 'b', 0, 240)).toBe(0)
  expect(fieldScrollLeft(columns, 'c', 20, 240)).toBe(100)
  expect(fieldScrollLeft(columns, 'a', 120, 240)).toBe(0)
  expect(fieldScrollLeft(columns, 'number', 120, 240)).toBe(120)
  expect(fieldScrollLeft(columns, 'hidden', 120, 240)).toBe(120)
})
test('accounts for frozen right columns and avoids oscillation for oversized columns', () => {
  expect(fieldScrollLeft([...columns, { field: 'last', fixed: 'right', renderWidth: 30 }], 'c', 0, 240)).toBe(130)
  expect(fieldScrollLeft([{ field: 'wide', renderWidth: 600 }], 'wide', 100, 240)).toBe(100)
})

test('rows scroll only by the distance needed to reveal the clipped edge', () => {
  expect(rowScrollTop(3, 40, 100, 200)).toBe(100)
  expect(rowScrollTop(2, 40, 100, 200)).toBe(80)
  expect(rowScrollTop(7, 40, 100, 200)).toBe(120)
  expect(rowScrollTop(30, 40, 100, 200)).toBe(1040)
  expect(rowScrollTop(2, 80, 200, 200)).toBe(160)
  expect(rowScrollTop(-1, 40, 100, 200)).toBe(100)
  expect(rowScrollTop(0, 400, 100, 200)).toBe(100)
})
