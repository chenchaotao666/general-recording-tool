// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test } from 'vitest'
import ElementPlus from 'element-plus'
import ScheduleTimePicker from '../src/components/smart/automation/ScheduleTimePicker.vue'

test('time columns support any minute and only commit on confirmation', async () => {
  const wrapper = mount(ScheduleTimePicker, { props: { modelValue: '17:45' },
    global: { plugins: [ElementPlus], stubs: {
      ElPopover: { name: 'ElPopover', template: '<div><slot name="reference" /><slot /></div>' },
    } } })
  wrapper.findComponent({ name: 'ElPopover' }).vm.$emit('show')
  await flushPromises()
  expect(wrapper.find('[aria-label="小时"] [aria-selected="true"]').text()).toBe('17时')
  expect(wrapper.find('[aria-label="分钟"] [aria-selected="true"]').text()).toBe('45分')
  await wrapper.findAll('[aria-label="分钟"] button')[47].trigger('click')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  await wrapper.find('.el-button--primary').trigger('click')
  expect(wrapper.emitted('update:modelValue')[0]).toEqual(['17:47'])
  wrapper.findComponent({ name: 'ElPopover' }).vm.$emit('show')
  await flushPromises()
  expect(wrapper.find('[aria-label="分钟"] [aria-selected="true"]').text()).toBe('45分')
  wrapper.unmount()
})
