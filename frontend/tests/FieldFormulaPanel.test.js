// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import FieldConfigDialog from '../src/components/smart/panels/FieldConfigDialog.vue'

test('teleported formula interactions do not dismiss the parent field panel', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  const wrapper = mount(FieldConfigDialog, {
    props: { visible: false, fields: [], preset: { field_type: 'formula', label: 'Formula' } },
    global: { plugins: [ElementPlus], stubs: {
      'el-dialog': { template: '<div class="el-dialog"><slot /></div>' },
      FormulaEditor: { inheritAttrs: false, props: ['visible'], emits: ['close'], template: '<teleport to="body"><div v-if="visible" class="test-formula"><input /><button @click="$emit(\'close\')">Close</button></div></teleport>' },
      AiFormulaDialog: true,
    } },
  })
  try {
    await wrapper.setProps({ visible: true })
    await wrapper.find('.fx-entry').trigger('click')
    document.querySelector('.test-formula input').click()
    await nextTick()
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(document.querySelector('.test-formula')).not.toBeNull()
    document.querySelector('.test-formula button').click()
    await nextTick()
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(document.querySelector('.test-formula')).toBeNull()
    document.body.click()
    expect(wrapper.emitted('close')).toHaveLength(1)
  } finally { wrapper.unmount(); vi.unstubAllGlobals() }
})
