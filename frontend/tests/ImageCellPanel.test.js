// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import ElementPlus from 'element-plus'
import ImageCellPanel from '../src/components/smart/grid/ImageCellPanel.vue'

test('detail gallery shows every image and filename; read-only allows preview without upload or removal', async () => {
  const upload = vi.fn()
  const value = Array.from({ length: 4 }, (_, i) => ({ url: `/image-${i}.png`, name: `图片${i}.png` }))
  const wrapper = mount(ImageCellPanel, { props: { value, detail: true, readonly: true, upload }, global: { plugins: [ElementPlus] } })
  expect(wrapper.findAll('.image-card')).toHaveLength(4)
  expect(wrapper.findAll('.image-card-name').map(n => n.text())).toEqual(value.map(v => v.name))
  expect(wrapper.find('.image-cell-thumbs').exists()).toBe(false)
  expect(wrapper.find('.image-card-actions').exists()).toBe(false)
  expect(wrapper.find('.image-local-upload').exists()).toBe(false)
  await wrapper.find('.image-drop-wrap').trigger('drop', { dataTransfer: { files: [new File(['a'], 'a.png', { type: 'image/png' })] } })
  expect(upload).not.toHaveBeenCalled()
  await wrapper.setProps({ readonly: false })
  await wrapper.find('[aria-label="删除图片"]').trigger('click')
  expect(wrapper.emitted('commit').at(-1)[0]).toEqual(value.slice(1))
  wrapper.unmount()
})

function setup(upload) {
  return mount(ImageCellPanel, { props: { value: ['existing'], upload }, global: { plugins: [ElementPlus],
    stubs: { 'el-popover': { template: '<div><slot name="reference" /><slot /></div>' } } } })
}
test('drop uploads all images once without losing existing values or accepting other files', async () => {
  const upload = vi.fn().mockResolvedValueOnce({ files: [{ id: 11 }] }).mockResolvedValueOnce({ files: [{ id: 12 }] })
  const wrapper = setup(upload)
  expect(wrapper.find('.image-upload-panel').exists()).toBe(false)
  await wrapper.vm.focus()
  await wrapper.find('.image-drop-wrap').trigger('drop', { dataTransfer: { files: [
    new File(['a'], 'a.png', { type: 'image/png' }), new File(['b'], 'b.jpg', { type: 'image/jpeg' }),
    new File(['x'], 'x.txt', { type: 'text/plain' }),
  ] } })
  await flushPromises()
  expect(upload).toHaveBeenCalledTimes(2)
  expect(wrapper.emitted('commit')).toEqual([[['existing', '11', '12']]])
  wrapper.unmount()
})
test('failed upload remains retryable and produces no invalid image IDs', async () => {
  const upload = vi.fn().mockRejectedValueOnce(new Error('Network error')).mockResolvedValueOnce({ files: [{ id: 13 }] })
  const wrapper = setup(upload)
  await wrapper.vm.focus()
  const event = { dataTransfer: { files: [new File(['a'], 'a.png', { type: 'image/png' })] } }
  await wrapper.find('.image-drop-wrap').trigger('drop', event)
  await flushPromises()
  expect(wrapper.find('[role="alert"]').text()).toContain('Network error')
  expect(wrapper.emitted('commit')).toBeUndefined()
  await wrapper.find('.image-drop-wrap').trigger('drop', event)
  await flushPromises()
  expect(wrapper.emitted('commit')[0][0]).toEqual(['existing', '13'])
  wrapper.unmount()
})

test('gallery removal preserves the other images and uploading keeps the gallery open', async () => {
  const wrapper = setup(vi.fn().mockResolvedValue({ files: [{ id: 14, filename: 'photo.png' }] }))
  await wrapper.vm.focus()
  await wrapper.find('.image-drop-wrap').trigger('drop', { dataTransfer: { files: [new File(['a'], 'photo.png', { type: 'image/png' })] } })
  await flushPromises()
  expect(wrapper.findAll('.image-card')).toHaveLength(2)
  expect(wrapper.text()).toContain('photo.png')
  await wrapper.find('[aria-label="删除图片"]').trigger('click')
  expect(wrapper.emitted('commit').at(-1)[0]).toEqual(['14'])
  expect(wrapper.findAll('.image-card')).toHaveLength(1)
  wrapper.unmount()
})

test('first click selects only; selected image click previews and blank click opens the panel', async () => {
  const wrapper = setup(vi.fn())
  await wrapper.find('.image-cell-thumbs img').trigger('click')
  expect(wrapper.emitted('select')).toHaveLength(1)
  expect(wrapper.findComponent({ name: 'ElImageViewer' }).exists()).toBe(false)
  expect(wrapper.emitted('open')).toBeUndefined()
  await wrapper.setProps({ selected: true })
  await wrapper.find('.image-cell-trigger').trigger('click')
  expect(wrapper.emitted('open')).toHaveLength(1)
  await wrapper.find('.image-cell-arrow').trigger('click')
  expect(wrapper.emitted('collapse')).toHaveLength(1)
  await wrapper.find('.image-cell-thumbs img').trigger('click')
  expect(wrapper.findComponent({ name: 'ElImageViewer' }).exists()).toBe(true)
  wrapper.unmount()
})
