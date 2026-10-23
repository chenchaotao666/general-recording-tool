// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, test } from 'vitest'
import AutomationEditor from '../src/components/smart/automation/AutomationEditor.vue'
import PermCondRow from '../src/components/smart/perms/PermCondRow.vue'

test('specified columns preserve legacy watches and edit independent OR conditions', async () => {
  const wrapper = mount(AutomationEditor, {
    props: {
      tableId: 1, fields: [{ field_name: 'product', label: '产品', field_type: 'text' }], loadFields: async () => [],
      modelValue: { trigger: { type: 'recordUpdated', watchFields: ['product'], filter: { match: 'all', conditions: [] } }, actions: [] },
      'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }),
    },
    global: { plugins: [ElementPlus], stubs: { ElPopover: { template: '<div><slot name="reference" /><slot /></div>' } } },
  })
  expect(wrapper.find('.ae-watch-trigger').text()).toBe('指定列')
  await wrapper.find('.ae-watch-trigger').trigger('click')
  const panel = wrapper.find('.ae-watch-panel')
  expect(panel.findComponent(PermCondRow).props('cond')).toEqual({ fieldId: 'product', operator: 'changed' })
  const cond = { fieldId: 'product', operator: 'contains', value: '产品A' }
  panel.findComponent(PermCondRow).vm.$emit('update', cond)
  await flushPromises()
  expect(wrapper.props('modelValue').trigger.watchConditions).toEqual([cond])
  expect(wrapper.props('modelValue').trigger.watchFields).toEqual([])
  await panel.find('.ae-find-add').trigger('click')
  expect(wrapper.props('modelValue').trigger.watchConditions).toHaveLength(2)
  panel.findAllComponents(PermCondRow)[1].vm.$emit('remove')
  await flushPromises()
  expect(wrapper.props('modelValue').trigger.watchConditions).toEqual([cond])
  panel.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'any')
  await flushPromises()
  expect(wrapper.find('.ae-watch-trigger').text()).toBe('任意列')
  expect(wrapper.props('modelValue').trigger.watchConditions).toEqual([])
  panel.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'specified')
  await flushPromises()
  expect(wrapper.props('modelValue').trigger.watchConditions).toHaveLength(1)
  expect(wrapper.props('modelValue').trigger.filter).toEqual({ match: 'all', conditions: [] })
  wrapper.unmount()
})
