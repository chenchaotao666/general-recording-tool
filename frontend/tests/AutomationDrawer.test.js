// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ElementPlus from 'element-plus'
import AutomationDrawer from '../src/components/smart/automation/AutomationDrawer.vue'
import AutomationEditor from '../src/components/smart/automation/AutomationEditor.vue'
import { smartCreateAutomation, smartRunAutomation } from '../src/api/index.js'

vi.mock('../src/api/index.js', () => ({
  smartListAutomations: vi.fn(async () => ({ automations: [] })),
  smartCreateAutomation: vi.fn(async (_, payload) => ({ automation: { id: 1, ...payload } })),
  smartUpdateAutomation: vi.fn(), smartAutomationRuns: vi.fn(),
  smartDeleteAutomation: vi.fn(), smartRunAutomation: vi.fn(async () => ({ run: { status: 'success' } })),
}))

describe('automation flow creation', () => {
  it('shows trial run for new schedule flows and saves disabled before running', async () => {
    const wrapper = mount(AutomationDrawer, {
      props: { visible: false, tableId: 1, loadFields: async () => [] },
      global: { plugins: [ElementPlus] },
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.find('.ad-list-toolbar button').trigger('click')
    await wrapper.find('.ad-template-blank').trigger('click')
    const editor = wrapper.findComponent(AutomationEditor)
    for (const type of ['recordCreated', 'schedule', 'recordUpdated']) {
      editor.vm.$emit('update:modelValue', { ...editor.props('modelValue'),
        trigger: { type, schedule: { freq: 'weekdays', time: '17:45' } } })
      await flushPromises()
      expect(wrapper.findAll('.ad-foot button').some(b => b.text() === '试运行')).toBe(type === 'schedule')
    }
    editor.vm.$emit('update:modelValue', { ...editor.props('modelValue'),
      trigger: { type: 'schedule', schedule: { freq: 'weekdays', time: '17:45' } },
      actions: [{ id: 'new1', type: 'createRecord', tableId: 1, values: [] }] })
    await flushPromises()
    await wrapper.findAll('.ad-foot button').find(b => b.text() === '试运行').trigger('click')
    await flushPromises()
    expect(smartCreateAutomation).toHaveBeenLastCalledWith(1, expect.objectContaining({ enabled: false }))
    expect(smartRunAutomation).toHaveBeenLastCalledWith(1)
    expect(wrapper.emitted('run-complete')).toHaveLength(1)
    expect(wrapper.findComponent(AutomationEditor).exists()).toBe(true)
    wrapper.unmount()
  })
  it('allows draft saving but blocks enabling final find steps and same-table loops', async () => {
    const wrapper = mount(AutomationDrawer, {
      props: { visible: false, tableId: 1, loadFields: async () => [] },
      global: { plugins: [ElementPlus] },
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.find('.ad-list-toolbar button').trigger('click')
    await wrapper.find('.ad-template-blank').trigger('click')
    const editor = wrapper.findComponent(AutomationEditor)
    const draft = { ...editor.props('modelValue'), trigger: { type: 'recordCreated' },
      actions: [{ id: 'a1', type: 'findRecords', tableId: 1, conditions: [] }] }
    editor.vm.$emit('update:modelValue', draft)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('最后一步不能为查找记录')
    expect(wrapper.find('.ad-foot button').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('.ad-foot .el-button--primary').attributes('disabled')).toBeDefined()
    const calls = smartCreateAutomation.mock.calls.length
    await wrapper.find('.ad-foot .el-button--primary').trigger('click')
    expect(smartCreateAutomation.mock.calls.length).toBe(calls)
    editor.vm.$emit('update:modelValue', { ...draft, actions: [...draft.actions, { id: 'a2', type: 'createRecord', tableId: 1, values: [] }] })
    await flushPromises()
    expect(wrapper.find('.ad-save-error').text()).toContain('第 3 步存在循环执行')
    expect(wrapper.find('.ad-foot button').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('.ad-foot .el-button--primary').attributes('disabled')).toBeDefined()
    editor.vm.$emit('update:modelValue', { ...draft, actions: [...draft.actions, { id: 'a2', type: 'createRecord', tableId: 2, values: [] }] })
    await flushPromises()
    expect(wrapper.find('.ad-save-error').exists()).toBe(false)
    expect(wrapper.findAll('.ad-foot button').every(b => b.attributes('disabled') === undefined)).toBe(true)
    editor.vm.$emit('update:modelValue', draft)
    await flushPromises()
    await wrapper.findAll('.ad-foot button').find(b => b.text() === '仅保存').trigger('click')
    await flushPromises()
    expect(smartCreateAutomation).toHaveBeenLastCalledWith(1, expect.objectContaining({ enabled: false, actions: draft.actions }))
    wrapper.unmount()
  })
  it('starts blank, requires steps, and distinguishes save from enable', async () => {
    const wrapper = mount(AutomationDrawer, {
      props: { visible: false, tableId: 1, tableName: '客户', loadFields: async () => [] },
      global: { plugins: [ElementPlus] },
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.find('.ad-list-toolbar button').trigger('click')
    await wrapper.find('.ad-template-blank').trigger('click')
    expect(wrapper.findAll('.ae-choice:disabled')).toHaveLength(4)
    expect(wrapper.find('.ad-foot .el-button--primary').attributes('disabled')).toBeDefined()
    await wrapper.find('.ae-choice').trigger('click')
    const choices = wrapper.findAll('.ae-choice')
    await choices.find(b => b.text().includes('新增记录')).trigger('click')
    expect(wrapper.findComponent(AutomationEditor).props('modelValue').actions[0].type).toBe('createRecord')
    await wrapper.findAll('.ad-foot button').find(b => b.text() === '仅保存').trigger('click')
    await flushPromises()
    expect(smartCreateAutomation).toHaveBeenLastCalledWith(1, expect.objectContaining({ enabled: false }))
    await wrapper.find('.ad-list-toolbar button').trigger('click')
    await wrapper.findAll('.ad-template').find(b => b.text().includes('新记录设置默认值')).trigger('click')
    await wrapper.find('.ad-foot .el-button--primary').trigger('click')
    await flushPromises()
    expect(smartCreateAutomation).toHaveBeenLastCalledWith(1, expect.objectContaining({ enabled: true }))
    wrapper.unmount()
  })
})
