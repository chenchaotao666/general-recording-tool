import { expect, test } from 'vitest'
import { functionInsertion, callContext } from '../src/smart/utils/formula.js'

test('insert a method after a field or completed call, with caret inside parentheses', () => {
  for (const before of ['[contact]', '[contact].TRIM()', '[#1.name]', '"hello"']) {
    const inserted = functionInsertion(before, 'CONCAT')
    expect(inserted.text).toBe('.CONCAT()')
    expect(callContext(before + inserted.text.slice(0, inserted.caret))).toEqual({ name: 'CONCAT', argIndex: 1, chained: true })
  }
})
test('explicit dots and ordinary nested functions do not receive an extra dot', () => {
  for (const before of ['', 'IF(', 'CONCAT([name], ', '[name] & ', '[name].']) {
    expect(functionInsertion(before, 'CONCAT').text).toBe('CONCAT()')
  }
  expect(functionInsertion('', 'TODAY', false)).toEqual({ text: 'TODAY()', caret: 7 })
})
