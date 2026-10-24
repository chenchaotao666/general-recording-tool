// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus, { ElSelect, ElOption } from 'element-plus'
import FieldConfigDialog from '../src/components/smart/panels/FieldConfigDialog.vue'

test('lookup uses smart tables and refreshes tables and source fields on reopening', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  const sourceFieldsOf = vi.fn(async () => [])
  const wrapper = mount(FieldConfigDialog, { props: { visible: false, fields: [],
    field: { field_name: 'lookup', label: 'Lookup', field_type: 'lookup', options: { sourceTableId: 2 } },
    tables: [{ id: 99, label: 'Ordinary table' }], lookupTables: [{ id: 2, label: 'Smart table' }], sourceFieldsOf,
  }, global: { plugins: [ElementPlus], stubs: { 'el-dialog': { template: '<div class="el-dialog"><slot /></div>' } } } })
  try {
    await wrapper.setProps({ visible: true })
    await flushPromises()
    expect(sourceFieldsOf).toHaveBeenCalledTimes(1)
    const picker = wrapper.findAllComponents(ElSelect).find(c => c.props('placeholder') === '选择表')
    expect(picker.findAllComponents(ElOption).map(c => c.props('label'))).toEqual(['Smart table'])
    const previousCalls = sourceFieldsOf.mock.calls.length
    picker.vm.$emit('visible-change', true)
    await flushPromises()
    expect(wrapper.emitted('refresh-lookup-tables').length).toBeGreaterThanOrEqual(2)
    expect(sourceFieldsOf.mock.calls.length).toBeGreaterThan(previousCalls)
    await wrapper.setProps({ lookupTables: [{ id: 2, label: 'Smart table' }, { id: 3, label: 'New smart table' }] })
    expect(picker.findAllComponents(ElOption).map(c => c.props('label'))).toContain('New smart table')
    sourceFieldsOf.mockClear()
    await wrapper.setProps({ openKey: 1 })
    await flushPromises()
    expect(sourceFieldsOf).toHaveBeenCalledTimes(1)
  } finally { wrapper.unmount(); vi.unstubAllGlobals() }
})
