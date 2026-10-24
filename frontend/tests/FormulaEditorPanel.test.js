// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import FormulaEditor from '../src/components/smart/formula/FormulaEditor.vue'
import { smartGetDoc, smartAiGenerateFormula } from '../src/api/index.js'

vi.mock('../src/api/index.js', () => ({
  smartFormulaFunctions: vi.fn(async () => ({ categories: ['文本'], functions: [{ name: 'CONCAT', category: '文本', signature: 'CONCAT(文本1, 文本2)', desc: '拼接文本', examples: [] }], operators: [] })),
  smartFormulaPreview: vi.fn(async () => ({ ok: true, blank: true, row_values: {} })),
  smartAiGenerateFormula: vi.fn(async () => ({ formula: '1 + 2', display: '1 + 2', explanation: 'Add numbers' })),
  smartGetDoc: vi.fn(), smartGetTree: vi.fn(), getTable: vi.fn(),
}))

test('AI opens in a separate floating panel and preserves input without overwriting until applied', async () => {
  const wrapper = mount(FormulaEditor, { props: { visible: true, fields: [{ field_name: 'customer', label: 'Customer', field_type: 'text' }] }, global: {
    plugins: [ElementPlus],
  } })
  try {
    await flushPromises()
    const panel = document.querySelector('.fxe-mask')
    expect(panel.querySelector('.fxe-col-fields').textContent).toContain('表字段')
    expect(panel.textContent).not.toContain('整表引用')
    expect(panel.querySelector('.fxe-col-funcs').textContent).toContain('CONCAT')
    expect(smartGetDoc).not.toHaveBeenCalled()
    ;[...panel.querySelectorAll('.fxe-tool')].find(el => el.textContent.includes('AI 写公式')).click()
    await flushPromises()
    expect(panel.style.display).not.toBe('none')
    expect(document.querySelector('.el-dialog')).toBeNull()
    expect(panel.querySelector('.fxe-ai .afa')).not.toBeNull()
    expect(panel.querySelector('.fxe .fxe-ai')).toBeNull()
    expect(panel.querySelector('.fxe-ai').getAttribute('role')).toBe('dialog')
    expect(panel.querySelector('.afa-fields')).toBeNull()
    expect(panel.querySelector('.fxe-doc').style.display).not.toBe('none')
    const assistant = wrapper.findComponent({ name: 'AiFormulaAssistant' })
    await assistant.find('textarea').trigger('focus')
    panel.querySelector('.fxe-col-fields .fxe-item').click()
    await flushPromises()
    expect(assistant.find('textarea').element.value).toBe('[Customer]')
    expect(panel.querySelector('.fxe-editor').textContent).toBe('')
    await assistant.find('textarea').setValue('Add one and two')
    await assistant.find('.afa-actions button').trigger('click')
    await flushPromises()
    expect(smartAiGenerateFormula).toHaveBeenCalledWith(null, 'Add one and two')
    expect(panel.querySelector('.fxe-editor').textContent).toBe('')
    expect(panel.querySelector('.afa-code').textContent).toBe('1 + 2')
    await assistant.findAll('button').at(-1).trigger('click')
    await flushPromises()
    expect(panel.querySelector('.fxe-editor').textContent).toBe('1 + 2')
    panel.querySelector('[aria-label="关闭 AI 写公式"]').click()
    await flushPromises()
    expect(panel.querySelector('.fxe-editor').textContent).toBe('1 + 2')
    expect(panel.querySelector('.fxe-ai').style.display).toBe('none')
    ;[...panel.querySelectorAll('.fxe-tool')].find(el => el.textContent.includes('AI 写公式')).click()
    await flushPromises()
    expect(assistant.find('textarea').element.value).toBe('Add one and two')
  } finally { wrapper.unmount() }
})
