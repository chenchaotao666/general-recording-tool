// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, test } from 'vitest'
import AutomationEditor from '../src/components/smart/automation/AutomationEditor.vue'
import PermCondRow from '../src/components/smart/perms/PermCondRow.vue'

test('find records config edits match mode and conditions inside its popover', async () => {
  const wrapper = mount(AutomationEditor, {
    props: {
      tableId: 1, fields: [], tables: [], loadFields: async () => [],
      modelValue: { name: '查找', trigger: { type: 'recordCreated', filter: { conditions: [] } },
        actions: [{ id: 'find1', type: 'findRecords', tableId: 1, match: 'all', conditions: [], onNotFound: 'continue' }] },
      'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }),
    },
    global: { plugins: [ElementPlus], stubs: {
      ElPopover: { template: '<div><slot name="reference" /><slot /></div>' },
    } },
  })
  expect(wrapper.find('.ae-find-trigger').text()).toBe('满足条件的记录0')
  const panel = wrapper.find('.ae-find-conditions')
  panel.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'any')
  await flushPromises()
  expect(wrapper.props('modelValue').actions[0].match).toBe('any')
  await panel.find('.ae-find-add').trigger('click')
  expect(wrapper.props('modelValue').actions[0].conditions).toHaveLength(1)
  expect(wrapper.find('.ae-find-trigger .ae-config-count').text()).toBe('1')
  const condition = { fieldId: 'f_1', operator: 'contains', value: '客户' }
  panel.findComponent(PermCondRow).vm.$emit('update', condition)
  await flushPromises()
  expect(wrapper.props('modelValue').actions[0].conditions[0]).toEqual(condition)
  panel.findComponent(PermCondRow).vm.$emit('remove')
  await flushPromises()
  expect(wrapper.props('modelValue').actions[0].conditions).toEqual([])
  expect(wrapper.find('.ae-find-trigger .ae-config-count').text()).toBe('0')
  expect(wrapper.props('modelValue').actions[0].onNotFound).toBe('continue')
  wrapper.unmount()
})
