// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, test, vi } from 'vitest'
import SmartCellEditor from '../src/components/smart/grid/SmartCellEditor.vue'

test('selected text shows full content; second click edits and scroll collapses without saving', async () => {
  const listeners = new Set()
  const text = 'Long text line\nSecond line with all the content'
  const wrapper = mount(SmartCellEditor, {
    attachTo: document.body,
    props: { field: { field_name: 'text', field_type: 'text', options: {} }, record: { text }, preview: true },
    global: { plugins: [ElementPlus], provide: {
      smartGridScrollCollapse: fn => { listeners.add(fn); return () => listeners.delete(fn) },
    } },
  })
  try {
    await flushPromises()
    await new Promise(resolve => requestAnimationFrame(resolve))
    await flushPromises()
    const preview = document.querySelector('.cell-overlay.preview .preview-text')
    expect(preview.textContent).toBe(text)
    expect(document.querySelector('.cell-overlay textarea')).toBeNull()
    preview.click()
    expect(wrapper.emitted('enter-edit')).toHaveLength(1)
    for (const collapse of listeners) collapse()
    expect(wrapper.emitted('collapse')).toHaveLength(1)
    expect(wrapper.emitted('commit')).toBeUndefined()
  } finally { wrapper.unmount() }
  expect(listeners.size).toBe(0)
})

test.each([false, true])('preview transitions focus the editor regardless of fill handle (%s)', async fillHandle => {
  const wrapper = mount(SmartCellEditor, {
    attachTo: document.body,
    props: { field: { field_name: 'text', field_type: 'text', options: {} }, record: { text: 'Full text' }, preview: true, fillHandle },
    global: { plugins: [ElementPlus] },
  })
  try {
    await flushPromises()
    await new Promise(resolve => requestAnimationFrame(resolve))
    await flushPromises()
    expect(document.querySelector('.cell-overlay textarea')).toBeNull()
    await wrapper.setProps({ preview: false })
    await flushPromises()
    const textarea = document.querySelector('.cell-overlay textarea')
    expect(textarea).not.toBeNull()
    expect(document.activeElement).toBe(textarea)
    expect(document.querySelector('.preview-text')).toBeNull()
    // A reused preview must establish a fresh click window, not its mount time.
    vi.spyOn(Date, 'now').mockReturnValue(100000)
    await wrapper.setProps({ preview: true })
    await flushPromises()
    vi.mocked(Date.now).mockReturnValue(100100)
    document.querySelector('.preview-text').click()
    expect(wrapper.emitted('enter-edit')).toHaveLength(1)
    expect(document.querySelector('.cell-overlay textarea')).toBeNull()
  } finally { wrapper.unmount(); vi.restoreAllMocks() }
})

test('second press opens editing even when the subsequent click is lost or delayed', async () => {
  const wrapper = mount(SmartCellEditor, {
    attachTo: document.body,
    props: { field: { field_name: 'text', field_type: 'text', options: {} }, record: { text: 'Text' }, preview: true, fillHandle: true },
    global: { plugins: [ElementPlus] },
  })
  try {
    await flushPromises()
    await new Promise(resolve => requestAnimationFrame(resolve))
    await flushPromises()
    // Native double-click count must work beyond the old fixed 400ms window.
    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 1000)
    const press = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0, detail: 2 })
    document.querySelector('.preview-text').dispatchEvent(press)
    expect(wrapper.emitted('enter-edit')).toHaveLength(1)
    expect(press.defaultPrevented).toBe(true)
    document.querySelector('.text-fill-handle').dispatchEvent(new MouseEvent('mousedown', { bubbles: true, detail: 2 }))
    expect(wrapper.emitted('enter-edit')).toHaveLength(1)
  } finally { wrapper.unmount(); vi.restoreAllMocks() }
})

test('formula preview shows the complete result without a writable editor and collapses on scroll', async () => {
  const listeners = new Set()
  const text = 'A long calculated company name\nSecond line of the calculated result'
  const wrapper = mount(SmartCellEditor, {
    attachTo: document.body,
    props: { field: { field_name: 'formula', field_type: 'formula', options: {} }, record: { formula: text }, preview: true },
    global: { plugins: [ElementPlus], provide: {
      smartGridScrollCollapse: fn => { listeners.add(fn); return () => listeners.delete(fn) },
    } },
  })
  try {
    await flushPromises()
    await new Promise(resolve => requestAnimationFrame(resolve))
    await flushPromises()
    expect(document.querySelector('.preview-text').textContent).toBe(text)
    expect(document.querySelector('.cell-overlay textarea, .cell-overlay input, .text-fill-handle')).toBeNull()
    for (const collapse of listeners) collapse()
    expect(wrapper.emitted('collapse')).toHaveLength(1)
    expect(wrapper.emitted('commit')).toBeUndefined()
  } finally { wrapper.unmount() }
})
