// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { test, expect, vi } from 'vitest'
import CellDropdown from '../src/components/smart/grid/CellDropdown.vue'

test('shared dropdown blocks grid double clicks and manages hidden/disabled accessibility', async () => {
  const host = document.createElement('div'), doubleClick = vi.fn()
  document.body.appendChild(host); host.addEventListener('dblclick', doubleClick)
  const wrapper = mount(CellDropdown, { attachTo: host })
  await wrapper.trigger('click'); await wrapper.trigger('dblclick')
  expect(wrapper.emitted('click')).toHaveLength(1)
  expect(doubleClick).not.toHaveBeenCalled()
  await wrapper.setProps({ open: true })
  expect(wrapper.attributes('aria-expanded')).toBe('true')
  expect(wrapper.classes()).toContain('up')
  await wrapper.setProps({ visible: false })
  expect(wrapper.attributes('tabindex')).toBe('-1')
  expect(wrapper.attributes('aria-hidden')).toBe('true')
  await wrapper.trigger('click')
  expect(wrapper.emitted('click')).toHaveLength(1)
  await wrapper.setProps({ visible: true, disabled: true })
  expect(wrapper.attributes('disabled')).toBeDefined()
  wrapper.unmount(); host.remove()
})

test('decorative arrow leaves clicking to its parent', async () => {
  const wrapper = mount(CellDropdown, { props: { decorative: true } })
  expect(wrapper.element.tagName).toBe('SPAN')
  await wrapper.trigger('click')
  expect(wrapper.emitted('click')).toBeUndefined()
  wrapper.unmount()
})
