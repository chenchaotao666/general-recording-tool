// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import TbFieldSelect from '../src/components/smart/panels/TbFieldSelect.vue'
import FieldPickList from '../src/components/smart/panels/FieldPickList.vue'

test('field picker fits the available viewport and still selects the last field', async () => {
  const wrapper = mount(TbFieldSelect, {
    props: { fields: Array.from({ length: 30 }, (_, i) => ({ field_name: `f${i}`, label: `Field ${i}`, field_type: 'text' })) },
    global: { stubs: { ElPopover: {
      name: 'ElPopover',
      props: ['visible', 'placement'], emits: ['update:visible'],
      template: '<div><slot name="reference" /><slot /></div>',
    } } },
  })
  const rect = vi.spyOn(wrapper.find('.tbfs').element, 'getBoundingClientRect')
    .mockReturnValue({ top: 240, bottom: 276 })
  vi.stubGlobal('innerHeight', 690)
  const popover = wrapper.findComponent({ name: 'ElPopover' })
  popover.vm.$emit('update:visible', true)
  await flushPromises()
  expect(popover.props('placement')).toBe('bottom-start')
  expect(wrapper.findComponent(FieldPickList).props('maxHeight')).toBe(344)
  rect.mockReturnValue({ top: 570, bottom: 606 })
  window.dispatchEvent(new Event('scroll'))
  await flushPromises()
  expect(popover.props('placement')).toBe('top-start')
  expect(wrapper.findComponent(FieldPickList).props('maxHeight')).toBe(420)
  rect.mockReturnValue({ top: 210, bottom: 246 })
  vi.stubGlobal('innerHeight', 400)
  window.dispatchEvent(new Event('resize'))
  await flushPromises()
  expect(wrapper.findComponent(FieldPickList).props('maxHeight')).toBe(140)
  await wrapper.findAll('.fpl-item').at(-1).trigger('click')
  expect(wrapper.emitted('update:modelValue')[0]).toEqual(['f29'])
  expect(popover.props('visible')).toBe(false)
  wrapper.unmount()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
