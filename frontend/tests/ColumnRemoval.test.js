import { expect, test } from 'vitest'
import { isColumnRemoval, isColumnInsertion } from '../src/smart/utils/columnRemoval.js'

test('deletion keeps existing table registration including group members', () => {
  const before = [['a', null, 'a'], ['g', 'left', ['b', 'c']], ['d', null, 'd']]
  expect(isColumnRemoval(before, [['g', 'left', ['c']], ['d', null, 'd']])).toBe(true)
  expect(isColumnRemoval(before, [['a', null, 'a'], ['d', null, 'd']])).toBe(true)
})
test('insertion, reordering and freezing are not removal-only updates', () => {
  const before = [['g', null, ['a', 'b']], ['c', null, 'c']]
  expect(isColumnRemoval(before, [['g', null, ['b', 'a']], ['c', null, 'c']])).toBe(false)
  expect(isColumnRemoval(before, [['g', null, ['a', 'b', 'd']], ['c', null, 'c']])).toBe(false)
  expect(isColumnRemoval(before, [['g', 'left', ['a', 'b']], ['c', null, 'c']])).toBe(false)
  expect(isColumnRemoval(before, [['c', null, 'c'], ['g', null, ['a', 'b']]])).toBe(false)
})

test('insertions retain the table for right-edge, middle and grouped columns', () => {
  const before = [['a', null, 'a'], ['g', null, ['b', 'c']]]
  expect(isColumnInsertion(before, [...before, ['d', null, 'd']])).toBe(true)
  expect(isColumnInsertion(before, [before[0], ['d', null, 'd'], before[1]])).toBe(true)
  expect(isColumnInsertion(before, [before[0], ['g', null, ['b', 'd', 'c']]])).toBe(true)
  expect(isColumnInsertion([], before)).toBe(true)
  expect(isColumnInsertion(before, [['a', 'left', 'a'], before[1]])).toBe(false)
  expect(isColumnInsertion(before, [before[1], before[0], ['d', null, 'd']])).toBe(false)
  expect(isColumnInsertion(before, [before[0], ['g', null, ['c', 'b', 'd']]])).toBe(false)
})
