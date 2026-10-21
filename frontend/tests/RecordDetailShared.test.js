// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { test, expect, vi } from 'vitest'
import ElementPlus from 'element-plus'
import RecordDetailPanel from '../src/components/smart/panels/RecordDetailPanel.vue'
import RecordDetailFloating from '../src/components/smart/panels/RecordDetailFloating.vue'
import RecordDetailContent from '../src/components/smart/panels/RecordDetailContent.vue'
vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
for (const component of [RecordDetailPanel, RecordDetailFloating]) {
  test(`${component.__name} shares content and forwards edits, permissions and navigation`, async () => {
    const commit = vi.fn(), nav = vi.fn()
    const field = { id: 1, field_name: 'title', field_type: 'text', label: 'Title' }
    const wrapper = mount(component, { props: { visible: true, source: 'Source', record: { id: 1, title: 'Original' }, fields: [field], hasNext: true, canCreate: false, canDelete: false, onCellCommit: commit, onNav: nav }, global: { plugins: [ElementPlus], stubs: { teleport: true } } })
    expect(wrapper.findComponent(RecordDetailContent).exists()).toBe(true)
    await wrapper.find('.rd-value').trigger('click')
    await wrapper.find('textarea').setValue('Updated')
    await wrapper.find('textarea').trigger('blur')
    expect(commit).toHaveBeenCalledWith({ row: { id: 1, title: 'Original' }, field, value: 'Updated' })
    const buttons = wrapper.findAll('button').filter(b => b.attributes('data-smart-tip') === '下一条')
    await buttons[0].trigger('click')
    expect(nav).toHaveBeenCalledWith(1)
    await wrapper.setProps({ readonly: true, record: { id: 2, title: 'Second' } })
    expect(wrapper.find('.rd-title').text()).toBe('Second')
    expect(wrapper.find('.rd-value').classes()).not.toContain('editable')
    wrapper.unmount()
  })
}
