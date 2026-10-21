// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import SmartCellEditor from '../src/components/smart/grid/SmartCellEditor.vue'
import LinkCellPanel from '../src/components/smart/grid/LinkCellPanel.vue'
vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
test('typing into a selected cell initializes replacement text without changing the original record', () => {
  const record = { n: 123 }
  const wrapper = mount(SmartCellEditor, { props: { field: { field_name: 'n', field_type: 'number' }, record, initialInput: '4', advanceOnEnter: true }, global: { plugins: [ElementPlus] } })
  expect(wrapper.find('input').element.value).toBe('4')
  expect(record.n).toBe(123)
  expect(wrapper.emitted('commit')).toBeUndefined()
  wrapper.unmount()
})
test('Enter validates numbers, ignores IME composition, commits once and advances', async () => {
  const wrapper = mount(SmartCellEditor, { attachTo: document.body, props: { field: { field_name: 'n', field_type: 'number' }, record: { n: 1 }, advanceOnEnter: true }, global: { plugins: [ElementPlus] } })
  const input = wrapper.find('input')
  await input.setValue('42')
  await input.trigger('keydown', { key: 'Enter', isComposing: true })
  expect(wrapper.emitted('commit')).toBeUndefined()
  await input.setValue('invalid')
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('advance')).toBeUndefined()
  await input.setValue('42')
  await input.trigger('keydown', { key: 'Enter' })
  await input.trigger('blur')
  expect(wrapper.emitted('commit')).toEqual([[42]])
  expect(wrapper.emitted('advance')).toHaveLength(1)
  wrapper.unmount()
})
test('link Enter advances only after a valid URL is confirmed', async () => {
  const wrapper = mount(LinkCellPanel, { props: { selected: true, advanceOnEnter: true }, global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference"/><slot/></div>' } } } })
  await wrapper.vm.focus()
  const input = wrapper.findAll('input')[1]
  await input.setValue('javascript:alert(1)')
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('advance')).toBeUndefined()
  await input.setValue('https://example.com')
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('commit')).toHaveLength(1)
  expect(wrapper.emitted('advance')).toHaveLength(1)
  wrapper.unmount()
})

for (const [key, shiftKey, direction] of [['Tab', false, 'right'], ['Tab', true, 'left'], ['Enter', true, 'up'], ['Enter', false, 'down']]) {
  test(`${shiftKey ? 'Shift+' : ''}${key} commits once then navigates ${direction}`, async () => {
    const wrapper = mount(SmartCellEditor, { attachTo: document.body, props: { field: { field_name: 'n', field_type: 'number' }, record: { n: 1 }, advanceOnEnter: true }, global: { plugins: [ElementPlus] } })
    const input = wrapper.find('input')
    await input.setValue('9')
    await input.trigger('keydown', { key, shiftKey })
    await input.trigger('blur')
    expect(wrapper.emitted('commit')).toEqual([[9]])
    expect(wrapper.emitted('advance')).toEqual([[direction]])
    wrapper.unmount()
  })
}
