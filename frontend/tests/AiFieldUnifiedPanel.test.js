// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, expect, test, vi } from 'vitest'
import Panel from '../src/components/smart/ai/AiFieldPanel.vue'
import Editor from '../src/components/smart/ai/AiFieldEditor.vue'
import AiScenePicker from '../src/components/smart/ai/AiScenePicker.vue'
import Composer from '../src/components/smart/ai/AiComposer.vue'
import SmartCell from '../src/components/smart/grid/SmartCell.vue'
import { smartAiConfigure, smartAiPreview } from '../src/api/index.js'
vi.mock('../src/api/index.js', () => ({
  smartAiScenes: vi.fn(async () => ({ categories: [{ key: 'recommended', label: 'Recommended' }], scenes: [
    { key: 'custom', label: 'Custom', input: 'multi' },
    { key: 'summary', label: 'Summary', category: 'recommended', input: 'single', outputType: 'text', prompt: 'Summarize input' },
    { key: 'formula', label: 'Formula', category: 'recommended', action: 'formula' },
  ] })),
  smartAiConfigure: vi.fn(), smartAiPreview: vi.fn(),
}))
vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
const fields = [{ field_name: 'source', label: 'Source', field_type: 'text' }]
const config = { title: 'Generated summary', scene: 'custom', inputFields: ['source'], systemPrompt: 'Summarize', outputType: 'text', options: [] }
function mountPanel(props = {}) {
  return mount(Panel, { attachTo: document.body, props: { tableId: 1, fields, rows: [{ id: 1, source: 'Example' }], ...props }, global: { plugins: [ElementPlus] } })
}
// jsdom does not implement native contenteditable editing commands.
beforeEach(() => {
  document.execCommand = vi.fn((command, _, html) => {
    const selection = window.getSelection()
    if (!selection.rangeCount) return false
    const range = selection.getRangeAt(0)
    if (command === 'delete') { range.deleteContents(); return true }
    if (command === 'insertHTML') {
      range.deleteContents()
      const template = document.createElement('template')
      template.innerHTML = html
      range.insertNode(template.content)
      return true
    }
    return false
  })
})
beforeEach(() => { vi.clearAllMocks(); smartAiConfigure.mockResolvedValue({ config, preview: [{ inputs: { source: 'Example' }, output: 'Result' }] }) })

test.each(['percent', 'progress', 'date'])('AI output type %s is selectable and saved', async outputType => {
  const w = mountPanel({ field: { field_name: 'ai1', label: 'Output', options: config } })
  await flushPromises()
  const selector = w.findAllComponents({ name: 'ElSelect' })[0]
  expect(selector.findAllComponents({ name: 'ElOption' }).some(option => option.props('value') === outputType)).toBe(true)
  selector.vm.$emit('update:modelValue', outputType)
  selector.vm.$emit('change', outputType)
  await flushPromises()
  await w.find('.afe-btn.primary').trigger('click')
  expect(w.findComponent(Editor).emitted('save')[0][0].config.outputType).toBe(outputType)
  w.unmount()
})

test.each([
  ['percent', 25, '25%'], ['progress', 75, '75'], ['date', '2026-10-23', '2026-10-23'],
])('AI %s results use typed cell rendering', (outputType, value, text) => {
  const w = mount(SmartCell, { props: { field: { field_name: 'ai', field_type: 'ai', options: { outputType } }, record: { ai: value } }, global: { plugins: [ElementPlus] } })
  expect(w.text()).toContain(text)
  if (outputType === 'progress') expect(w.find('.progress-fill').attributes('style')).toContain('75%')
  w.unmount()
})
test('new field generates into the same editable panel and saves the chosen range', async () => {
  const w = mountPanel()
  await flushPromises()
  const panel = w.find('.afe').element
  const editor = w.findComponent(Editor)
  editor.findComponent(Composer).vm.$emit('send-secondary', { inputFields: ['source'], instruction: 'Summarize' })
  await flushPromises()
  expect(w.find('.afe').element).toBe(panel)
  expect(w.find('.afe-name').element.value).toBe('Generated summary')
  expect(smartAiConfigure.mock.calls[0][1].include_preview).toBe(false)
  expect(smartAiPreview).not.toHaveBeenCalled()
  expect(w.text()).not.toContain('Result')
  smartAiPreview.mockResolvedValue({config,preview:[{inputs:{source:'Example'},output:'Result'}]})
  await w.find('.afe-instruction-preview').trigger('click')
  await flushPromises()
  expect(smartAiPreview).toHaveBeenCalledTimes(1)
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
  editor.findComponent(Composer).vm.$emit('send-secondary', { inputFields: ['source'], instruction: 'Shorten' })
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
  const picker = editor.findComponent(AiScenePicker)
  picker.vm.$emit('change', 'summary')
  await flushPromises()
  expect(w.find('.afe-prompt-input textarea').element.value).toBe('Summarize input')
  expect(w.find('.afe-name').element.value).toBe('Summary')
  picker.vm.$emit('change', 'formula')
  expect(editor.emitted('write-formula')).toHaveLength(1)
  w.unmount()
})

test('execution instructions display directly beside requirements and before preview', async () => {
  const w = mountPanel({ field: { field_name: 'ai1', label: 'Existing name', options: { ...config, instruction: 'Keep it short' } } })
  await flushPromises()
  const advanced = w.find('.afe-instructions')
  expect(advanced.element.tagName).toBe('SECTION')
  expect(advanced.find('summary').exists()).toBe(false)
  expect(advanced.find('.folded').exists()).toBe(false)
  expect(advanced.find('.afe-prompt-input').exists()).toBe(true)
  expect(w.find('.afe-ai').element.contains(advanced.element)).toBe(true)
  expect(advanced.element.compareDocumentPosition(w.find('.asc').element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(w.find('.afe-advanced').exists()).toBe(false)
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
  expect(w.findAllComponents({ name: 'ElSelect' })).toHaveLength(2)
  composer.vm.insertField(extra)
  await flushPromises()
  await w.find('.aic-chip[data-fn="source"] .aic-chip-x').trigger('mousedown')
  expect(w.find('.afe-btn.primary').attributes('disabled')).toBeDefined()
  await w.find('.aic-send').trigger('click')
  await flushPromises()
  expect(smartAiConfigure.mock.calls[0][1].input_fields).toEqual(['line'])
  await w.find('.afe-btn.primary').trigger('click')
  expect(editor.emitted('save')[0][0].config.inputFields).toEqual(['line'])
  await w.find('.aic-chip-x').trigger('mousedown')
  await w.find('.aic-send').trigger('click')
  expect(smartAiConfigure).toHaveBeenCalledTimes(1)
  expect(w.find('.afe-btn.primary').attributes('disabled')).toBeDefined()
  w.unmount()
})


test('new custom scene infers output after requirements; explicit overrides and templates reset correctly', async () => {
  const w = mountPanel()
  await flushPromises()
  try {
    const editor = w.findComponent(Editor)
    const selector = w.findAllComponents({name:'ElSelect'})[0]
    expect(w.find('.afe-row2 .el-select').exists()).toBe(false)
    expect(w.find('.afe-output').exists()).toBe(true)
    expect(selector.props('modelValue')).toBe('auto')
    const send = async () => {
      editor.findComponent(Composer).vm.$emit('send-secondary',{inputFields:['source'],instruction:'Return a number'})
      await flushPromises()
    }
    smartAiConfigure.mockResolvedValue({config:{...config,outputType:'number'},preview:[]})
    await send()
    expect(smartAiConfigure.mock.calls[0][1].base).not.toHaveProperty('outputType')
    await w.find('.afe-btn.primary').trigger('click')
    expect(editor.emitted('save')[0][0].config.outputType).toBe('number')
    selector.vm.$emit('change','percent')
    await send()
    expect(smartAiConfigure.mock.calls[1][1].base.outputType).toBe('percent')
    editor.findComponent(AiScenePicker).vm.$emit('change','summary')
    await flushPromises()
    expect(selector.props('modelValue')).toBe('auto')
    await send()
    expect(smartAiConfigure.mock.calls[2][1].base).not.toHaveProperty('outputType')
  } finally { w.unmount() }
})


test('generation preserves composer and instruction editing preserves the textarea', async () => {
  const w = mountPanel({field:{field_name:'ai1',label:'Output',options:config}})
  await flushPromises()
  try {
    const prompt = w.find('.afe-prompt-input textarea').element
    expect(prompt.readOnly).toBe(true)
    await w.find('.afe-instructions .afe-l button').trigger('click')
    expect(w.find('.afe-prompt-input textarea').element).toBe(prompt)
    expect(prompt.readOnly).toBe(false)
    expect(document.activeElement).toBe(prompt)
    let resolve
    smartAiConfigure.mockImplementationOnce(()=>new Promise(done=>{resolve=done}))
    const composer = w.find('.aic').element
    w.findComponent(Composer).vm.$emit('send-secondary',{inputFields:['source'],instruction:'Summarize'})
    await flushPromises()
    expect(w.find('.aic').element).toBe(composer)
    expect(w.find('.aic').isVisible()).toBe(true)
    expect(w.find('.afe-running').exists()).toBe(false)
    expect(w.find('.aic-send').attributes('disabled')).toBeDefined()
    expect(w.find('.afe-stale').exists()).toBe(false)
    resolve({config,preview:[]})
    await flushPromises()
    expect(w.find('.aic').element).toBe(composer)
    expect(w.find('.aic-send').attributes('disabled')).toBeUndefined()
  } finally { w.unmount() }
})


test('requirements Enter inserts one line break without generating instructions', async () => {
  const w = mountPanel()
  await flushPromises()
  try {
    document.execCommand = vi.fn()
    const event = new KeyboardEvent('keydown', {key:'Enter',bubbles:true,cancelable:true})
    w.find('.aic-editor').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('insertLineBreak', false)
    expect(smartAiConfigure).not.toHaveBeenCalled()
  } finally { w.unmount() }
})

test('combined generation runs preview after instructions and preserves instructions on preview failure', async () => {
  const w = mountPanel()
  try {
    await flushPromises()
    smartAiPreview.mockRejectedValueOnce(new Error('Preview unavailable'))
    const composer = w.findComponent(Composer)
    composer.vm.$emit('send', { inputFields: ['source'], instruction: 'Summarize' })
    await flushPromises()
    expect(smartAiPreview).toHaveBeenCalledTimes(1)
    expect(smartAiPreview.mock.calls[0][1].config.systemPrompt).toBe('Summarize')
    expect(w.text()).toContain('Preview unavailable')
    expect(w.find('.afe-prompt-input textarea').element.value).toBe('Summarize')
    smartAiPreview.mockResolvedValueOnce({ config, preview: [{ inputs: { source: 'Example' }, output: 'Recovered' }] })
    await w.find('.afe-instruction-preview').trigger('click')
    await flushPromises()
    expect(smartAiConfigure).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('Recovered')
  } finally { w.unmount() }
})

test('failed instruction generation never starts preview', async () => {
  const w = mountPanel()
  try {
    await flushPromises()
    smartAiConfigure.mockRejectedValueOnce(new Error('Instruction unavailable'))
    w.findComponent(Composer).vm.$emit('send', { inputFields: ['source'], instruction: 'Summarize' })
    await flushPromises()
    expect(smartAiPreview).not.toHaveBeenCalled()
    expect(w.text()).toContain('Instruction unavailable')
  } finally { w.unmount() }
})
