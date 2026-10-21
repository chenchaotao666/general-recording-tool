// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { test, expect, vi } from 'vitest'
import ElementPlus from 'element-plus'
import LinkCellPanel from '../src/components/smart/grid/LinkCellPanel.vue'

test('grid scrolling collapses an open panel and releases the scroll subscription', async () => {
  const listeners = new Set()
  const wrapper = mount(LinkCellPanel, { global: {
    plugins: [ElementPlus],
    provide: { smartGridScrollCollapse: callback => { listeners.add(callback); return () => listeners.delete(callback) } },
    stubs: { 'el-popover': { template: '<div><slot /></div>' } },
  } })
  try {
    expect(listeners.size).toBe(0)
    await wrapper.vm.focus()
    expect(listeners.size).toBe(1)
    for (const collapse of [...listeners]) collapse()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.link-cell-panel').exists()).toBe(false)
    expect(wrapper.emitted('collapse')).toHaveLength(1)
    expect(listeners.size).toBe(0)
  } finally { wrapper.unmount() }
})

test('outside-click listener is installed only while the editor is open', async () => {
  const add = vi.spyOn(document, 'addEventListener'), remove = vi.spyOn(document, 'removeEventListener')
  const wrapper = mount(LinkCellPanel, { global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference" /><slot /></div>' } } } })
  try {
    const anchor = wrapper.find('.link-cell-trigger').element
    expect(wrapper.find('.link-cell-panel').exists()).toBe(false)
    expect(add.mock.calls.filter(([name, , capture]) => name === 'mousedown' && capture === true)).toHaveLength(0)
    await wrapper.vm.focus()
    expect(wrapper.find('.link-cell-trigger').element).toBe(anchor)
    expect(wrapper.find('.link-cell-panel').exists()).toBe(true)
    const calls = add.mock.calls.filter(([name, , capture]) => name === 'mousedown' && capture === true)
    expect(calls).toHaveLength(1)
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(wrapper.emitted('cancel')).toBeTruthy()
    expect(remove).toHaveBeenCalledWith('mousedown', calls[0][1], true)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.link-cell-panel').exists()).toBe(false)
    expect(wrapper.find('.link-cell-trigger').element).toBe(anchor)
  } finally { wrapper.unmount(); add.mockRestore(); remove.mockRestore() }
})

test('link editor confirms explicit drafts, normalizes URLs and rejects executable schemes', async () => {
  const wrapper = mount(LinkCellPanel, { props: { value: { text: 'Original', url: 'https://example.com' }, selected: true }, global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference" /><slot /></div>' } } } })
  await wrapper.vm.focus()
  let inputs = wrapper.findAll('input')
  await inputs[0].setValue('Updated')
  await inputs[1].setValue('example.org/path')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('commit')[0][0]).toEqual({ text: 'Updated', url: 'https://example.org/path' })
  await wrapper.vm.focus()
  inputs = wrapper.findAll('input')
  expect(inputs[0].element.value).toBe('Original')
  await inputs[1].setValue('javascript:alert(1)')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('commit')).toHaveLength(1)
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  await wrapper.find('.link-edit-actions button').trigger('click')
  expect(wrapper.emitted('commit')).toHaveLength(1)
  wrapper.unmount()
})
