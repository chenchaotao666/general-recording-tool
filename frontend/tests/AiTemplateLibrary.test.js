// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import Editor from '../src/components/smart/ai/AiFieldEditor.vue'
import Picker from '../src/components/smart/ai/AiScenePicker.vue'
import Intro from '../src/components/smart/ai/AiTemplateIntro.vue'
import Help from '../src/components/smart/ai/AiTemplateHelp.vue'
import Card from '../src/components/smart/ai/AiSceneCard.vue'
import { smartAiPreview } from '../src/api/index.js'

// jsdom does not implement the browser's resize observer used by the picker.
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

test('selected template introduction opens in a side popover instead of expanding the form', async () => {
  const wrapper = mount(Help, { attachTo: document.body, props: { scene: { key: 'deadline', label: '倒计时', local: true, formulaDisplay: 'DATEDIF(TODAY(),[日期],"D")' } }, global: { plugins: [ElementPlus] } })
  try {
    expect(wrapper.find('.ati').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'ElPopover' }).props('placement')).toBe('right-start')
    await wrapper.find('.ati-help-trigger').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'ElPopover' }).props('visible')).toBe(true)
    expect(document.querySelector('.ai-selected-template-pop .ati').textContent).toContain('DATEDIF')
    expect(wrapper.find('.ati').exists()).toBe(false)
    await wrapper.setProps({ scene: { key: 'other', label: '其他模板' } })
    expect(wrapper.findComponent({ name: 'ElPopover' }).props('visible')).toBe(false)
  } finally { wrapper.unmount() }
})

vi.mock('../src/api/index.js', () => ({
  smartAiScenes: vi.fn(async () => ({ categories: [{ key: 'project', label: '项目管理' }], scenes: [
    { key: 'custom', label: '自定义', input: 'multi' },
    { key: 'workdays', label: '计算工作日天数', input: 'multi', category: 'project', local: true, outputType: 'number', desc: '含首尾，考虑调休。', inputHint: '开始和结束日期', executionLabel: '本地计算', notes: ['不消耗 AI 次数'], inputRoles: [
      { key: 'start', label: '开始日期', types: ['date'], required: true },
      { key: 'end', label: '结束日期', types: ['date'], required: true },
    ] },
  ] })),
  smartAiConfigure: vi.fn(), smartAiPreview: vi.fn(async (_, payload) => ({ config: payload.config, preview: [{ inputs: { a: '2026-10-12', b: '2026-10-16' }, output: 5 }] })),
}))

test('local template requires named mappings, previews and saves them without an LLM configuration call', async () => {
  const wrapper = mount(Editor, { attachTo: document.body, props: { tableId: 7, fields: [{ field_name: 'a', label: '开始', field_type: 'date' }, { field_name: 'b', label: '结束', field_type: 'date' }] }, global: { plugins: [ElementPlus] } })
  try {
    await flushPromises()
    wrapper.findComponent(Picker).vm.$emit('change', 'workdays')
    await flushPromises()
    expect(wrapper.find('.ati-help-trigger').text()).toContain('含首尾，考虑调休。')
    expect(wrapper.find('.afe-btn.primary').element.disabled).toBe(true)
    const bindings = wrapper.findAll('.afe-binding')
    bindings[1].findComponent({ name: 'ElSelect' }).vm.$emit('change', 'b')
    await flushPromises()
    expect(wrapper.find('.afe-btn.primary').element.disabled).toBe(true)
    bindings[0].findComponent({ name: 'ElSelect' }).vm.$emit('change', 'a')
    await flushPromises()
    expect(wrapper.find('.afe-btn.primary').element.disabled).toBe(false)
    await wrapper.find('.afe-instruction-preview').trigger('click')
    await flushPromises()
    expect(smartAiPreview.mock.calls.at(-1)[1].config.inputBindings).toEqual({ end: 'b', start: 'a' })
    expect(wrapper.find('.asc-th').text()).toContain('开始')
    expect(wrapper.find('.asc-th').text()).toContain('结束')
    await wrapper.find('.afe-btn.primary').trigger('click')
    expect(wrapper.emitted('save')[0][0].config.inputFields).toEqual(['a', 'b'])
  } finally { wrapper.unmount() }
})

test('unavailable template explains the missing capability', () => {
  const wrapper = mount(Intro, { props: { scene: { label: '汇率', disabled: true, disabledReason: '尚未接入汇率数据服务', desc: '查询汇率', executionLabel: '联网查询' } } })
  expect(wrapper.text()).toContain('尚未接入汇率数据服务')
  wrapper.unmount()
})

test('local calculation logic is expanded and updates when the hovered scene changes', async () => {
  const wrapper = mount(Intro, { props: { standalone: true, expanded: true, scene: { key: 'cvBmr', label: '计算基础代谢率', local: true, calculationLogic: '男性：10 × 体重 + 6.25 × 身高 − 5 × 年龄 + 5\n单位：kcal/天' } } })
  expect(wrapper.find('.ati-logic').attributes()).toHaveProperty('open')
  expect(wrapper.find('.ati-logic pre').text()).toContain('6.25 × 身高')
  await wrapper.setProps({ scene: { key: 'mkRank', label: '排名', local: true, calculationLogic: '排名 = 1 + 严格大于本行数值的记录数' } })
  expect(wrapper.find('.ati-logic pre').text()).toContain('排名 = 1')
  expect(wrapper.text()).not.toContain('kcal/天')
  wrapper.unmount()
})

test('formula template displays its executable formula without model instructions', () => {
  const wrapper = mount(Intro, { props: { standalone: true, expanded: true, scene: { key: 'tax', label: '个税档位', local: true, executionLabel: '使用公式计算', formulaDisplay: 'IFS([所得额]<=3000,"3%",TRUE,"10%")', prompt: 'legacy model prompt' } } })
  expect(wrapper.find('pre').text()).toContain('IFS([所得额]')
  expect(wrapper.find('.ati-prompt').attributes()).toHaveProperty('open')
  expect(wrapper.text()).not.toContain('legacy model prompt')
  wrapper.unmount()
})

test('attachment preview renders download links and retains the file result', () => {
  const wrapper = mount(Card, { props: { preview: { config: { outputType: 'file' }, rows: [{ output: [{ id: 'a'.repeat(32), name: '二维码.png' }] }] } }, global: { plugins: [ElementPlus] } })
  expect(wrapper.find('a.file-chip').text()).toContain('二维码.png')
  expect(wrapper.find('a.file-chip').attributes('href')).toContain('/api/smart/files/' + 'a'.repeat(32))
  wrapper.unmount()
})
