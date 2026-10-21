// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { test, expect, vi } from 'vitest'
import ElementPlus from 'element-plus'
import RelationCellPanel from '../src/components/smart/grid/RelationCellPanel.vue'
import { smartRelationRecords, smartUpdateView } from '../src/api/index.js'
vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
vi.mock('../src/api/index.js', () => ({ smartRelationRecords: vi.fn(), smartUpdateView: vi.fn(), smartUpdateRecord: vi.fn(), imageUrl: vi.fn() }))
test('does not request per-cell data until interaction and preserves selection when removing a relation', async () => {
  smartRelationRecords.mockResolvedValue({ fields: [{ id: 1, field_name: 'title', field_type: 'text', label: 'Title' }], items: [{ id: 201, title: 'Beyond first page' }, { id: 3, title: 'Third' }], my_perms: {}, content_perm: {}, view: { config: {} } })
  const wrapper = mount(RelationCellPanel, { props: { value: [201, 3], field: { label: 'Related', options: { targetTableId: 2 } }, selected: false }, global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference"/><slot/></div>' } } } })
  expect(smartRelationRecords).not.toHaveBeenCalled()
  await wrapper.find('.relation-trigger').trigger('click')
  expect(wrapper.emitted('select')).toHaveLength(1)
  expect(wrapper.emitted('open')).toBeUndefined()
  await wrapper.setProps({ selected: true }); await flushPromises()
  expect(smartRelationRecords).toHaveBeenCalledWith(2, { ids: '201,3', view_id: undefined })
  expect(wrapper.text()).toContain('Beyond first page')
  await wrapper.find('.relation-chip button').trigger('click')
  expect(wrapper.emitted('commit')[0][0]).toEqual([3])
  expect(wrapper.emitted('cancel')).toBeUndefined()
  wrapper.unmount()
})

test('picker retains IDs across pages and cancel does not write', async () => {
  smartRelationRecords.mockResolvedValue({ fields: [], items: [{ id: 51 }], total: 100, my_perms: {}, content_perm: {}, view: { config: {} } })
  const wrapper = mount(RelationCellPanel, { props: { value: [1], field: { options: { targetTableId: 2 } }, selected: true }, global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference"/><slot/></div>' } } } })
  wrapper.vm.openPicker(); await flushPromises()
  wrapper.vm.page = 2; await wrapper.vm.loadPage()
  wrapper.vm.choose(51)
  expect(wrapper.vm.chosen).toEqual([1, 51])
  wrapper.vm.picker = false
  expect(wrapper.emitted('commit')).toBeUndefined()
  wrapper.vm.openPicker(); await flushPromises()
  expect(wrapper.vm.chosen).toEqual([1])
  wrapper.vm.choose(51); wrapper.vm.confirm()
  expect(wrapper.emitted('commit')[0][0]).toEqual([1, 51])
  wrapper.unmount()
})

test('title selection saves the target view while preserving other settings and requires view permission', async () => {
  smartUpdateView.mockClear()
  smartUpdateView.mockResolvedValue({})
  const data = { fields: [], items: [], content_perm: { viewManage: true }, my_perms: { can_create: true }, view: { id: 9, config: { rowHeight: 52 } } }
  smartRelationRecords.mockResolvedValue(data)
  const wrapper = mount(RelationCellPanel, { props: { value: [], field: { options: { targetTableId: 2, viewId: 9 } } }, global: { plugins: [ElementPlus], stubs: { 'el-popover': { template: '<div><slot name="reference"/><slot/></div>' }, teleport: true } } })
  wrapper.vm.openPicker(); await flushPromises()
  expect(wrapper.find('.relation-list-footer').text()).not.toContain('添加记录')
  await wrapper.vm.setTitleField('name')
  expect(smartUpdateView).toHaveBeenCalledWith(9, { config: { rowHeight: 52, recordTitleField: 'name' } })
  expect(smartRelationRecords).toHaveBeenLastCalledWith(2, { ids: '', view_id: 9 })
  wrapper.vm.remember({ ...data, content_perm: { viewManage: false } })
  await wrapper.vm.setTitleField('other')
  expect(smartUpdateView).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
