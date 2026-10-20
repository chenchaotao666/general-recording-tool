// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import AutomationRunLogs from '../src/components/smart/automation/AutomationRunLogs.vue'
import { smartAutomationRuns } from '../src/api/index.js'

vi.mock('../src/api/index.js', () => ({
  smartAutomationRuns: vi.fn(async () => ({ total: 1, runs: [{
    id: 12, status: 'success', started_at: '2026-10-20 21:04:19.000000',
    finished_at: '2026-10-20 21:04:21.900000',
    trigger_snapshot: { operator: 'Tester', event_type: 'recordCreated' },
    step_results: [{ step: 2, type: 'sendMessage', status: 'success', message: '已发送给 1 人' }],
  }] })),
}))

test('logs load with filters, open details, and return without losing the list', async () => {
  const wrapper = mount(AutomationRunLogs, { props: { ruleId: 3 }, global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(smartAutomationRuns).toHaveBeenCalledWith(3, expect.objectContaining({ page: 1, limit: 20 }))
  expect(wrapper.find('tbody').text()).toContain('2.9 秒')
  await wrapper.find('tbody .arl-link').trigger('click')
  expect(wrapper.find('.arl-summary').text()).toContain('ID：12')
  expect(wrapper.text()).toContain('未记录')
  expect(wrapper.text()).toContain('已发送给 1 人')
  expect(wrapper.vm.back()).toBe(true)
  await flushPromises()
  expect(wrapper.find('tbody').exists()).toBe(true)
  expect(wrapper.vm.back()).toBe(false)
  const selects = wrapper.findAllComponents({ name: 'ElSelect' })
  selects[0].vm.$emit('update:modelValue', ['failed', 'partial'])
  selects[0].vm.$emit('change')
  await flushPromises()
  expect(smartAutomationRuns).toHaveBeenLastCalledWith(3, expect.objectContaining({ statuses: 'failed,partial', page: 1 }))
  wrapper.unmount()
})
