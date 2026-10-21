// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { expect, test } from 'vitest'
import SmartCell from '../src/components/smart/grid/SmartCell.vue'

function cell(type, value, options = {}, aggregation = 'raw') {
  return mount(SmartCell, { props: {
    field: { field_name: 'result', field_type: 'lookup', options: { aggregation },
      lookupDisplayField: { field_name: 'source', field_type: type, options } },
    record: { result: value },
  }, global: { stubs: { 'el-image': true }, provide: { smartMemberDir: computed(() => new Map([[2, { id: 2, name: 'Alice' }]])) } } })
}

test('raw lookup renders source select tags, members, dates and links', () => {
  const tags = cell('singleSelect', ['a'], { options: [{ id: 'a', label: 'Ready', color: 'blue' }] })
  expect(tags.find('.opt-tag').text()).toBe('Ready'); tags.unmount()
  const members = cell('member', [[2]])
  expect(members.find('.member-chip').text()).toContain('Alice'); members.unmount()
  const dates = cell('date', ['2026-10-22T12:30:00'], { format: 'yyyy年M月d日 HH:mm' })
  expect(dates.text()).toBe('2026年10月22日 12:30'); dates.unmount()
  const link = cell('url', [{ text: 'Website', url: 'https://example.com' }])
  expect(link.find('a').attributes('href')).toBe('https://example.com'); link.unmount()
})

test('lookup preserves scalar types for multiple matches and aggregation stays numeric', () => {
  const checks = cell('checkbox', [false, true])
  expect(checks.findAll('.checkbox')).toHaveLength(2)
  expect(checks.findAll('.checkbox.checked')).toHaveLength(1); checks.unmount()
  const currency = cell('currency', [12.5], { precision: 2, currencySymbol: '$' })
  expect(currency.text()).toBe('$12.50'); currency.unmount()
  const count = cell('date', 2, {}, 'count')
  expect(count.text()).toBe('2'); count.unmount()
  const empty = cell('checkbox', null)
  expect(empty.find('.checkbox').exists()).toBe(false); empty.unmount()
})
