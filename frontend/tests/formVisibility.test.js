import { describe, expect, it } from 'vitest'
import { normalizeVisibility, isItemVisible } from '../src/components/smart/form/formLogic.js'

describe('form question dependencies', () => {
  const condition = { fieldId: 'a', operator: 'eq', value: 'yes' }
  it('keeps valid preceding dependencies and filling behavior', () => {
    const items = normalizeVisibility([{ fieldId: 'a' }, { fieldId: 'b', visibility: { match: 'all', conditions: [condition] } }])
    expect(isItemVisible(items[1], { a: 'yes' })).toBe(true)
    expect(isItemVisible(items[1], { a: 'no' })).toBe(false)
  })
  it('clears dependencies when a question moves first or its source is removed', () => {
    const dependent = { fieldId: 'b', visibility: { conditions: [condition] } }
    expect(normalizeVisibility([dependent, { fieldId: 'a' }])[0].visibility).toBeNull()
    expect(normalizeVisibility([{ fieldId: 'c' }, dependent])[1].visibility).toBeNull()
    expect(dependent.visibility.conditions).toEqual([condition])
  })
  it('keeps empty editor rows after the first question', () => {
    const pending = { fieldId: null, operator: 'eq' }
    const items = normalizeVisibility([{ fieldId: 'a' }, { fieldId: 'b', visibility: { conditions: [pending] } }])
    expect(items[1].visibility.conditions).toEqual([pending])
    expect(isItemVisible(items[1], {})).toBe(true)
  })
})
