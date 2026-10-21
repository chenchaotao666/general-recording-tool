// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { test, expect } from 'vitest'
import ElementPlus from 'element-plus'
import LinkCellPanel from '../src/components/smart/grid/LinkCellPanel.vue'

test('link editor confirms explicit drafts, normalizes URLs and rejects executable schemes', async () => {
  const wrapper = mount(LinkCellPanel, { props: { value: { text: 'Original', url: 'https://example.com' }, selected: true }, global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference" /><slot /></div>' } } } })
  await wrapper.vm.focus()
  const inputs = wrapper.findAll('input')
  await inputs[0].setValue('Updated')
  await inputs[1].setValue('example.org/path')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('commit')[0][0]).toEqual({ text: 'Updated', url: 'https://example.org/path' })
  await wrapper.vm.focus()
  expect(inputs[0].element.value).toBe('Original')
  await inputs[1].setValue('javascript:alert(1)')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('commit')).toHaveLength(1)
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  await wrapper.find('.link-edit-actions button').trigger('click')
  expect(wrapper.emitted('commit')).toHaveLength(1)
  wrapper.unmount()
})
