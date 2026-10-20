// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { usePanelResize } from '../src/smart/utils/usePanelResize.js'

test('right panel resizes, remembers width and cleans up when closed during dragging', () => {
  localStorage.removeItem('test-panel-width')
  const component = defineComponent({
    setup: () => usePanelResize('test-panel-width', 580),
    template: '<div @mousedown="startResize" />',
  })
  const wrapper = mount(component)
  document.body.style.cursor = 'crosshair'
  wrapper.element.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: 600 }))
  document.dispatchEvent(new MouseEvent('mousemove', { clientX: 550 }))
  expect(wrapper.vm.panelWidth).toBe(630)
  expect(document.body.style.userSelect).toBe('none')
  wrapper.unmount()
  expect(document.body.style.cursor).toBe('crosshair')
  expect(document.body.style.userSelect).toBe('')
  expect(localStorage.getItem('test-panel-width')).toBe('630')
  document.dispatchEvent(new MouseEvent('mousemove', { clientX: 100 }))
  const reopened = mount(component)
  expect(reopened.vm.panelWidth).toBe(630)
  reopened.unmount()
  document.body.style.cursor = ''
  localStorage.removeItem('test-panel-width')
})
