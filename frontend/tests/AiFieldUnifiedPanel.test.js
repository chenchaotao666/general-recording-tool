// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, expect, test, vi } from 'vitest'
import Panel from '../src/components/smart/ai/AiFieldPanel.vue'
import Editor from '../src/components/smart/ai/AiFieldEditor.vue'
import Composer from '../src/components/smart/ai/AiComposer.vue'
import { smartAiConfigure } from '../src/api/index.js'
vi.mock('../src/api/index.js', () => ({
  smartAiScenes: vi.fn(async () => ({ categories: [{ key: 'recommended', label: 'Recommended' }], scenes: [
    { key: 'custom', label: 'Custom', input: 'multi' },
    { key: 'summary', label: 'Summary', category: 'recommended', input: 'single', outputType: 'text', prompt: 'Summarize input' },
    { key: 'formula', label: 'Formula', category: 'recommended', action: 'formula' },
  ] })),
  smartAiConfigure: vi.fn(), smartAiPreview: vi.fn(),
}))
const fields = [{ field_name: 'source', label: 'Source', field_type: 'text' }]
const config = { title: 'Generated summary', scene: 'custom', inputFields: ['source'], systemPrompt: 'Summarize', outputType: 'text', options: [] }
function mountPanel(props = {}) {
  return mount(Panel, { attachTo: document.body, props: { tableId: 1, fields, rows: [{ id: 1, source: 'Example' }], ...props }, global: { plugins: [ElementPlus] } })
}
beforeEach(() => { vi.clearAllMocks(); smartAiConfigure.mockResolvedValue({ config, preview: [{ inputs: { source: 'Example' }, output: 'Result' }] }) })
test('new field generates into the same editable panel and saves the chosen range', async () => {
  const w = mountPanel()
  await flushPromises()
  const panel = w.find('.afe').element
  const editor = w.findComponent(Editor)
  editor.findComponent(Composer).vm.$emit('send', { inputFields: ['source'], instruction: 'Summarize' })
  await flushPromises()
  expect(w.find('.afe').element).toBe(panel)
  expect(w.find('.afe-name').element.value).toBe('Generated summary')
  expect(w.text()).toContain('Result')
  expect(w.findAll('.afe')).toHaveLength(1)
  expect(w.find('.aip-use-mask').exists()).toBe(false)
  await w.find('.afe-btn.primary').trigger('click')
  expect(editor.emitted('save')[0][0]).toMatchObject({ label: 'Generated summary', config: { systemPrompt: 'Summarize', inputFields: ['source'] }, run: 'first5' })
  w.unmount()
})
test('existing field uses the same form, preserves name, and saves without rerunning', async () => {
  const w = mountPanel({ field: { field_name: 'ai1', label: 'Existing name', options: config } })
  await flushPromises()
  const editor = w.findComponent(Editor)
  editor.findComponent(Composer).vm.$emit('send', { inputFields: ['source'], instruction: 'Shorten' })
  await flushPromises()
  expect(w.find('.afe-name').element.value).toBe('Existing name')
  await w.find('.afe-btn.primary').trigger('click')
  expect(editor.emitted('save')[0][0].run).toBe('none')
  expect(smartAiConfigure.mock.calls[0][1].field_name).toBe('ai1')
  w.unmount()
})
test('template selection populates settings inline and formula keeps its own route', async () => {
  const w = mountPanel()
  await flushPromises()
  const editor = w.findComponent(Editor)
  const picker = editor.findAllComponents({ name: 'ElSelect' })[0]
  picker.vm.$emit('change', 'summary')
  await flushPromises()
  expect(w.text()).toContain('Summarize input')
  expect(w.find('.afe-name').element.value).toBe('Summary')
  picker.vm.$emit('change', 'formula')
  expect(editor.emitted('write-formula')).toHaveLength(1)
  w.unmount()
})

test('requirements precede preview, advanced settings are collapsed, and footer has no composer', async () => {
  const w = mountPanel({ field: { field_name: 'ai1', label: 'Existing name', options: { ...config, instruction: 'Keep it short' } } })
  await flushPromises()
  const advanced = w.find('.afe-advanced')
  expect(advanced.element.open).toBe(false)
  expect(advanced.find('.afe-prompt').exists()).toBe(true)
  expect(w.find('.afe-foot .aic').exists()).toBe(false)
  expect(w.find('.afe-sub').exists()).toBe(false)
  const composer = w.find('.afe-ai')
  expect(composer.element.compareDocumentPosition(advanced.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(w.find('.aic-editor').element.textContent).toContain('Keep it short')
  expect(w.findAll('.aic-chip')).toHaveLength(1)
  await w.find('.aic-send').trigger('click')
  await flushPromises()
  expect(w.find('.aic-editor').element.textContent).toContain('Keep it short')
  expect(w.findAll('.aic-chip')).toHaveLength(1)
  expect(smartAiConfigure.mock.calls[0][1].instruction).toBe('Keep it short [Source]')
  w.unmount()
})


test('existing references hydrate once, chip insertion and removal drive saved dependencies', async () => {
  const extra = { field_name: 'line', label: 'Line', field_type: 'text' }
  const w = mountPanel({ fields: [...fields, extra], field: { field_name: 'ai1', label: 'Summary', options: { ...config, instruction: '[Source] summary' } } })
  await flushPromises()
  const editor = w.findComponent(Editor)
  const composer = editor.findComponent(Composer)
  expect(w.findAll('.aic-chip')).toHaveLength(1)
  expect(w.findAllComponents({ name: 'ElSelect' })).toHaveLength(3)
  composer.vm.insertField(extra)
  await flushPromises()
  await w.find('.aic-chip[data-fn="source"] .aic-chip-x').trigger('mousedown')
  await w.find('.afe-btn.primary').trigger('click')
  expect(editor.emitted('save')[0][0].config.inputFields).toEqual(['line'])
  await w.find('.aic-send').trigger('click')
  await flushPromises()
  expect(smartAiConfigure.mock.calls[0][1].input_fields).toEqual(['line'])
  await w.find('.aic-chip-x').trigger('mousedown')
  await w.find('.aic-send').trigger('click')
  expect(smartAiConfigure).toHaveBeenCalledTimes(1)
  expect(w.find('.afe-btn.primary').attributes('disabled')).toBeDefined()
  w.unmount()
})
