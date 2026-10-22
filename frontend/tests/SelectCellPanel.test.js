// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import SelectCellPanel from '../src/components/smart/grid/SelectCellPanel.vue'

for (const closed of [true, false]) {
  test(`single-select removal clears immediately with panel closed=${closed}`, async () => {
    const wrapper = mount(SelectCellPanel, { props: {
      closed,
      field: { field_name: 'status', field_type: 'singleSelect', options: { options: [{ id: 'a', label: 'A' }] } },
      record: { status: 'a' },
    } })
    await wrapper.find('.tag-x').trigger('click')
    expect(wrapper.find('.opt-tag').exists()).toBe(false)
    expect(wrapper.emitted(closed ? 'commit' : 'commit-soft')).toEqual([[null]])
    expect(wrapper.emitted('collapse')).toBeUndefined()
    expect(wrapper.emitted('open')).toBeUndefined()
    await wrapper.setProps({ record: { status: null } })
    await wrapper.setProps({ record: { status: 'a' } })
    expect(wrapper.find('.opt-label').text()).toBe('A')
    wrapper.unmount()
  })
}
