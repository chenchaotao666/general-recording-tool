// @vitest-environment jsdom
import { computed, reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { resolveEnumTags } from '../src/smart/utils/enumTags.js'
import SmartCell from '../src/components/smart/grid/SmartCell.vue'
import CompactCellTags from '../src/components/smart/grid/CompactCellTags.vue'

test('cells share option tags and react to edits, deletion and added options', () => {
  const options = reactive([{ id: 'a', label: 'Alpha', color: 0 }])
  const first = computed(() => resolveEnumTags(options, 'a'))
  expect(first.value[0]).toBe(resolveEnumTags(options, ['a'])[0])
  options[0].label = 'Updated'
  expect(first.value[0].label).toBe('Updated')
  options.splice(0, 1)
  expect(first.value[0]).toMatchObject({ label: 'a', raw: true })
  options.push({ id: 'a', label: 'Restored', color: 1 })
  expect(first.value[0].label).toBe('Restored')
  expect(first.value[0].raw).toBeUndefined()
})

test('unknown imported values retain their display and numeric IDs stay distinct', () => {
  expect(resolveEnumTags([{ id: 1, label: 'One' }], ['1', 1, null, '', { name: 'raw' }])
    .map(tag => tag.label)).toEqual(['One', '1', '{"name":"raw"}'])
})

test('single tags and empty cells need no measuring component', async () => {
  const wrapper = mount(SmartCell, { global: { stubs: { 'el-image': true } }, props: {
    field: { field_name: 'choice', field_type: 'multiSelect', options: { options: [{ id: 1, label: 'One' }] } },
    record: { choice: [1] },
  } })
  try {
    expect(wrapper.findComponent(CompactCellTags).exists()).toBe(false)
    expect(wrapper.find('.opt-tag').text()).toBe('One')
    await wrapper.setProps({ record: { choice: [] } })
    expect(wrapper.findComponent(CompactCellTags).exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  } finally { wrapper.unmount() }
})
