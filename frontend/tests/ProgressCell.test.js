// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import ElementPlus from 'element-plus'
import ProgressCell from '../src/components/smart/grid/ProgressCell.vue'
import SmartCellEditor from '../src/components/smart/grid/SmartCellEditor.vue'
import { progressColor } from '../src/smart/registry/fieldRegistry.js'

test('selecting empty progress starts at the left endpoint without saving a value', async () => {
  for (const value of [null, undefined, '']) {
    const wrapper = mount(ProgressCell, { props: { value } })
    await wrapper.setProps({ interactive: true })
    expect(wrapper.find('input').element.value).toBe('0')
    expect(wrapper.find('.progress-fill').element.style.width).toBe('0%')
    expect(wrapper.find('.progress-number').text()).toBe('')
    expect(wrapper.emitted('commit')).toBeUndefined()
    await wrapper.setProps({ config: { range: { min: 20, max: 100 } } })
    expect(wrapper.find('input').element.value).toBe('20')
    wrapper.unmount()
  }
})

test('progress schemes select one solid color using the configured range', async () => {
  expect(progressColor('s-red-green', 0.49)).toBe('#F5554A')
  expect(progressColor('s-red-green', 0.5)).toBe('#3DC15E')
  expect(progressColor('s-rainbow', 0.75)).toBe('#4E8CF7')
  expect(progressColor('s-rainbow', 1)).toBe('#8B5CF6')
  expect(progressColor('g-blue', 0)).toBe('#dce8fd')
  expect(progressColor('g-blue', 1)).toBe('#4e8cf7')
  expect(progressColor('g-blue', 0.5)).toMatch(/^#[0-9a-f]{6}$/)
  const wrapper = mount(ProgressCell, { props: { value: 40, config: { range: { min: 20, max: 100 }, color: 's-red-green' }, interactive: true } })
  expect(wrapper.find('.progress-fill').element.style.background).toBe('rgb(245, 85, 74)')
  const slider = wrapper.find('input')
  slider.element.value = '80'
  await slider.trigger('input')
  expect(wrapper.find('.progress-fill').element.style.background).toBe('rgb(61, 193, 94)')
  expect(wrapper.find('.progress-fill').element.style.width).toBe('75%')
  wrapper.unmount()
})

test('progress is static until selected; dragging previews and commits on release', async () => {
  const wrapper = mount(ProgressCell, { props: { value: 35, config: { numberFormat: 'percent', color: 'green' } } })
  expect(wrapper.text()).toBe('35%')
  expect(wrapper.find('input').exists()).toBe(false)
  expect(wrapper.find('.progress-fill').attributes('style')).toContain('width: 35%')
  await wrapper.setProps({ interactive: true })
  const slider = wrapper.find('input')
  slider.element.value = '81'
  await slider.trigger('input')
  expect(wrapper.text()).toBe('81%')
  expect(wrapper.emitted('commit')).toBeUndefined()
  await slider.trigger('change')
  expect(wrapper.emitted('commit')[0]).toEqual([81])
  await slider.trigger('dblclick')
  expect(wrapper.emitted('enter-edit')).toHaveLength(1)
  await wrapper.setProps({ value: 50, config: { range: { min: 20, max: 60 }, numberFormat: 'percent', precision: 1 } })
  expect(wrapper.text()).toBe('75.0%')
  expect(slider.attributes('step')).toBe('0.1')
  wrapper.unmount()
})

test('double-click progress editor accepts numbers, clamps range and supports clearing', async () => {
  const make = value => mount(SmartCellEditor, { attachTo: document.body,
    props: { field: { field_name: 'p', field_type: 'progress', options: { range: { min: 0, max: 100 } } }, record: { p: value } },
    global: { plugins: [ElementPlus] } })
  const wrapper = make(35)
  expect(wrapper.find('input').element.value).toBe('35')
  await wrapper.find('input').setValue('120')
  await wrapper.find('input').trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('commit')[0]).toEqual([100])
  wrapper.unmount()
  const blank = make(null)
  expect(blank.find('input').element.value).toBe('')
  await blank.find('input').trigger('keydown', { key: 'Enter' })
  expect(blank.emitted('commit')[0]).toEqual([null])
  blank.unmount()
  const cancelled = make(35)
  await cancelled.find('input').setValue('70')
  await cancelled.find('input').trigger('keydown', { key: 'Escape' })
  await cancelled.find('input').trigger('blur')
  expect(cancelled.emitted('commit')).toBeUndefined()
  expect(cancelled.emitted('cancel')).toHaveLength(1)
  cancelled.unmount()
})

test('percentage progress edits the displayed percentage and converts back to the configured range', async () => {
  const wrapper = mount(SmartCellEditor, { attachTo: document.body,
    props: { field: { field_name: 'p', field_type: 'progress', options: { numberFormat: 'percent', range: { min: 20, max: 60 } } }, record: { p: 40 } },
    global: { plugins: [ElementPlus] } })
  expect(wrapper.find('input').element.value).toBe('50')
  expect(wrapper.find('.numeric-suffix').text()).toBe('%')
  await wrapper.find('input').setValue('75')
  await wrapper.find('input').trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('commit')).toEqual([[50]])
  wrapper.unmount()
})
