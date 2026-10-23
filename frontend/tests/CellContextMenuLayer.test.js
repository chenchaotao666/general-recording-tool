// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { computed, defineComponent, h, provide, ref } from 'vue'
import ElementPlus, { ElConfigProvider } from 'element-plus'
import { expect, test } from 'vitest'
import SmartCellEditor from '../src/components/smart/grid/SmartCellEditor.vue'
import CellContextMenu from '../src/components/smart/grid/CellContextMenu.vue'

test('late text overlay and preview-to-edit transition remain below the open menu', async () => {
  const editorVisible = ref(false), menuVisible = ref(true), preview = ref(true), layer = ref(0)
  const Host = defineComponent({
    setup() {
      provide('smartCellContextMenuLayer', computed(() => menuVisible.value ? layer.value : 0))
      return () => h('div', [
        menuVisible.value && h(CellContextMenu, { x: 100, y: 100, onLayer: value => { layer.value = value } }),
        editorVisible.value && h(SmartCellEditor, {
          field: { field_name: 'text', field_type: 'text', options: {} }, record: { text: 'Cell content' }, preview: preview.value,
        }),
      ])
    },
  })
  const wrapper = mount(defineComponent({ render: () => h(ElConfigProvider, { zIndex: 4000 }, { default: () => h(Host) }) }), {
    attachTo: document.body, global: { plugins: [ElementPlus] },
  })
  try {
    await flushPromises()
    editorVisible.value = true
    await flushPromises()
    await new Promise(resolve => requestAnimationFrame(resolve))
    await flushPromises()
    const overlay = () => document.querySelector('.cell-overlay')
    expect(Number(overlay().style.zIndex)).toBeLessThan(layer.value)
    preview.value = false
    await flushPromises()
    expect(overlay().querySelector('textarea').value).toBe('Cell content')
    expect(Number(overlay().style.zIndex)).toBeLessThan(layer.value)
    menuVisible.value = false
    await flushPromises()
    expect(Number(overlay().style.zIndex)).toBeGreaterThan(layer.value)
    expect(overlay().querySelector('textarea').value).toBe('Cell content')
  } finally { wrapper.unmount() }
})
