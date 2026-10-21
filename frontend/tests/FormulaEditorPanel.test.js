// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import FormulaEditor from '../src/components/smart/formula/FormulaEditor.vue'
import { smartGetDoc } from '../src/api/index.js'

vi.mock('../src/api/index.js', () => ({
  smartFormulaFunctions: vi.fn(async () => ({ categories: ['文本'], functions: [{ name: 'CONCAT', category: '文本', signature: 'CONCAT(文本1, 文本2)', desc: '拼接文本', examples: [] }], operators: [] })),
  smartFormulaPreview: vi.fn(async () => ({ blank: true, row_values: {} })),
  smartGetDoc: vi.fn(), smartGetTree: vi.fn(), getTable: vi.fn(),
}))

test('only local fields are offered, functions load on initial open, AI temporarily hides editor', async () => {
  const wrapper = mount(FormulaEditor, { props: { visible: true, fields: [] }, global: {
    plugins: [ElementPlus], stubs: { AiFormulaDialog: { inheritAttrs: false, props: ['visible'], emits: ['close', 'apply'], template: '<teleport to="body"><button v-if="visible" class="test-ai-close" @click="$emit(\'close\')">Close AI</button></teleport>' } },
  } })
  try {
    await flushPromises()
    const panel = document.querySelector('.fxe-mask')
    expect(panel.textContent).toContain('本表字段')
    expect(panel.textContent).not.toContain('整表引用')
    expect(panel.querySelector('.fxe-col-funcs').textContent).toContain('CONCAT')
    expect(smartGetDoc).not.toHaveBeenCalled()
    ;[...panel.querySelectorAll('.fxe-tool')].find(el => el.textContent.includes('AI 写公式')).click()
    await flushPromises()
    expect(panel.style.display).toBe('none')
    document.querySelector('.test-ai-close').click()
    await flushPromises()
    expect(panel.style.display).not.toBe('none')
  } finally { wrapper.unmount() }
})

