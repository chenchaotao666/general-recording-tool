// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import MessageEditor from '../src/components/smart/automation/MessageEditor.vue'
import VarMenu from '../src/components/smart/automation/VarMenu.vue'
vi.mock('../src/api/index.js', () => ({ listReports: vi.fn(async () => []) }))

test('real popover opens on add and closes on cancel without toggling twice', async () => {
  const wrapper = mount(MessageEditor, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  try {
    await wrapper.find('.me-add-button').trigger('click')
    await flushPromises()
    const popover = wrapper.findAllComponents({ name: 'ElPopover' })[0]
    expect(popover.props('visible')).toBe(true)
    expect(document.querySelector('.me-button-form')).not.toBeNull()
    document.querySelector('.me-button-actions button').click()
    await flushPromises()
    expect(popover.props('visible')).toBe(false)
    await wrapper.find('.me-add-button').trigger('click')
    await flushPromises()
    expect(popover.props('visible')).toBe(true)
  } finally { wrapper.unmount() }
})

test('message buttons require valid links, support variables, and stop at two', async () => {
  const wrapper = mount(MessageEditor, { global: { plugins: [ElementPlus], stubs: {
    ElPopover: { name: 'ElPopover', template: '<div><slot name="reference" /><slot /></div>' },
  } } })
  await wrapper.find('.me-add-button').trigger('click')
  const inputs = wrapper.findAll('.me-button-form input')
  await inputs[0].setValue('查看')
  await inputs[1].setValue('javascript:alert(1)')
  expect(wrapper.find('.me-button-actions .el-button--primary').attributes('disabled')).toBeDefined()
  await inputs[1].setValue('https://example.com')
  await wrapper.find('.me-button-actions .el-button--primary').trigger('click')
  expect(wrapper.emitted('change').at(-1)[0].buttons[0]).toEqual({
    label: '查看', link: { type: 'static', value: 'https://example.com' },
  })
  await wrapper.find('.me-add-button').trigger('click')
  await inputs[0].setValue('仪表盘')
  // Open the nested variable picker through its popover model.
  const popovers = wrapper.findAllComponents({ name: 'ElPopover' })
  popovers.at(-1).vm.$emit('update:visible', true)
  await wrapper.vm.$nextTick()
  wrapper.findComponent(VarMenu).vm.$emit('pick', { kind: 'dashboard', entryId: 7 }, '仪表盘7')
  await wrapper.vm.$nextTick()
  await wrapper.find('.me-button-actions .el-button--primary').trigger('click')
  expect(wrapper.findAll('.me-btn-chip')).toHaveLength(2)
  expect(wrapper.find('.me-add-button').attributes('disabled')).toBeDefined()
  expect(wrapper.emitted('change').at(-1)[0].buttons[1].link.var.entryId).toBe(7)
  wrapper.unmount()
})
