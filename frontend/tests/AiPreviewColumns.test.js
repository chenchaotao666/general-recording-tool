// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import AiSceneCard from '../src/components/smart/ai/AiSceneCard.vue'

test('preview gives each input its own aligned column and keeps result last', async () => {
  const fields = ['name', 'tags'].map(field_name => ({ field_name, label: field_name, field_type: 'text' }))
  const wrapper = mount(AiSceneCard, { props: { fields, preview: { config: { inputFields: ['name', 'tags'] }, rows: [{ inputs: { name: 'Customer', tags: 'VIP' }, output: 'Result' }] } }, global: { stubs: { SmartCell: { props: ['field', 'record'], template: '<span>{{ record[field.field_name] }}</span>' } } } })
  try {
    expect(wrapper.findAll('.asc-th .asc-td')).toHaveLength(3)
    const cells = wrapper.findAll('.asc-tr')[1].findAll('.asc-td')
    expect(cells.map(c => c.text())).toEqual(['Customer', 'VIP', 'Result'])
    await wrapper.setProps({ preview: { config: { inputFields: ['name'] }, rows: [] } })
    expect(wrapper.findAll('.asc-th .asc-td')).toHaveLength(2)
    expect(wrapper.find('.asc-empty').exists()).toBe(true)
    await wrapper.setProps({ preview: null, sample: { in: 'Input', out: 'Output', rows: [['A', 'B']] } })
    expect(wrapper.findAll('.asc-tr')[1].findAll('.asc-td').map(c => c.text())).toEqual(['A', 'B'])
  } finally { wrapper.unmount() }
})
