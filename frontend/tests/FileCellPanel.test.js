// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import FileCellPanel from '../src/components/smart/grid/FileCellPanel.vue'
import { fileUrl } from '../src/components/smart/grid/fileDisplay.js'
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }))
afterEach(() => vi.unstubAllGlobals())

test('first click selects, batch upload appends and gallery list deletion preserves other files', async () => {
  const upload = vi.fn().mockResolvedValueOnce({ id: 'b'.repeat(32), name: 'sheet.xlsx', size: 1024 }).mockRejectedValueOnce(new Error('Network'))
  const wrapper = mount(FileCellPanel, { props: { value: [{ id: 'a'.repeat(32), name: 'old.pdf', size: 10 }], upload, loadRecent: async () => [] }, global: { plugins: [ElementPlus], provide: { smartTableId: ref(1) }, stubs: { 'el-popover': { template: '<div><slot name="reference" /><slot /></div>' } } } })
  await wrapper.find('.file-cell-trigger').trigger('click')
  expect(wrapper.emitted('open')).toBeUndefined()
  expect(wrapper.find('.file-panel').exists()).toBe(false)
  await wrapper.setProps({ selected: true })
  await wrapper.find('.file-cell-trigger').trigger('click')
  await wrapper.find('.file-panel').trigger('drop', { dataTransfer: { files: [new File(['1'], 'sheet.xlsx'), new File(['2'], 'fail.pdf')] } })
  await flushPromises()
  expect(wrapper.emitted('commit')[0][0].map(f => f.name)).toEqual(['old.pdf', 'sheet.xlsx'])
  expect(wrapper.find('[role="alert"]').text()).toContain('Network')
  await wrapper.find('[aria-label="列表视图"]').trigger('click')
  await wrapper.find('.file-delete').trigger('click')
  expect(wrapper.emitted('commit').at(-1)[0].map(f => f.name)).toEqual(['sheet.xlsx'])
  expect(wrapper.text()).not.toContain('微盘')
  wrapper.unmount()
})

test('file links reject executable URLs and request inline previews only when asked', () => {
  expect(fileUrl({ url: 'javascript:alert(1)' })).toBe('')
  expect(fileUrl({ id: 'a'.repeat(32) }, true)).toContain('preview=true')
  expect(fileUrl({ id: '../other' })).toBe('')
})
