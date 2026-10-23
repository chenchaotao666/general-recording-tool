// @vitest-environment jsdom
import { afterEach, expect, test } from 'vitest'
import { mount } from '@vue/test-utils'
import AiPromptPanel from '../src/components/AiPromptPanel.vue'

let wrapper
afterEach(() => wrapper?.unmount())
async function openPanel() {
  wrapper = mount(AiPromptPanel, {
    props: { modelValue: false, image: false },
    global: { stubs: { teleport: true, ElRadioButton: true, ElRadioGroup: true, ElButton: { template: '<button><slot /></button>' } } },
  })
  await wrapper.setProps({ modelValue: true })
  await wrapper.find('textarea').setValue('把圆形改成红色')
  await wrapper.setProps({ confirmation: ['将修改 4 个元素。', '圆形填充红色', '其余元素保留', '更多详情', '最后一项'] })
}

test('inline review folds details and requires an explicit confirmation', async () => {
  await openPanel()
  expect(wrapper.text()).toContain('尚未应用到画布')
  expect(wrapper.text()).not.toContain('最后一项')
  await wrapper.find('textarea').trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('submit')).toBeUndefined()
  await wrapper.find('.ai-pp-review-toggle').trigger('click')
  expect(wrapper.text()).toContain('最后一项')
  const confirm = wrapper.findAll('button').find(b => b.text() === '确认应用')
  await confirm.trigger('click')
  expect(wrapper.emitted('confirm')).toHaveLength(1)
})

test('cancel returns to the original instruction without submitting', async () => {
  await openPanel()
  await wrapper.findAll('button').find(b => b.text() === '取消').trigger('click')
  expect(wrapper.emitted('cancel-confirmation')).toHaveLength(1)
  await wrapper.setProps({ confirmation: null })
  expect(wrapper.find('textarea').element.value).toBe('把圆形改成红色')
  expect(wrapper.find('.ai-pp-review').exists()).toBe(false)
  expect(wrapper.emitted('submit')).toBeUndefined()
  expect(wrapper.emitted('confirm')).toBeUndefined()
})

test('hiding a persistent panel preserves the draft and a result arriving in the background', async () => {
  await openPanel()
  await wrapper.setProps({ preserveDraft: true, confirmation: null, loading: true })
  await wrapper.setProps({ modelValue: false })
  await wrapper.setProps({ loading: false, confirmation: ['后台生成完成', '待确认的修改'] })
  await wrapper.setProps({ modelValue: true })
  expect(wrapper.find('textarea').element.value).toBe('把圆形改成红色')
  expect(wrapper.text()).toContain('后台生成完成')
  expect(wrapper.emitted('confirm')).toBeUndefined()
  expect(wrapper.emitted('submit')).toBeUndefined()
})

test('visual confirmation shows the actual image and hides change descriptions', async () => {
  await openPanel()
  await wrapper.setProps({ visualOnly: true, preview: 'data:image/png;base64,AA==' })
  expect(wrapper.find('.ai-pp-preview img').attributes('src')).toBe('data:image/png;base64,AA==')
  expect(wrapper.text()).not.toContain('将修改 4 个元素')
  expect(wrapper.find('.ai-pp-review-toggle').exists()).toBe(false)
  expect(wrapper.text()).toContain('确认应用')
  await wrapper.find('input[type="range"]').setValue(200)
  expect(wrapper.find('.ai-pp-preview-size').attributes('style')).toContain('200%')
  await wrapper.find('input[type="range"]').setValue(25)
  expect(wrapper.find('.ai-pp-preview-size').attributes('style')).toContain('25%')
})

test('application choice explicitly distinguishes adding and replacing', async () => {
  await openPanel()
  await wrapper.setProps({ visualOnly: true, applicationMode: 'append', allowModeChange: true })
  expect(wrapper.text()).toContain('确认添加')
  expect(wrapper.find('.ai-pp-apply-mode').exists()).toBe(false)
  await wrapper.findAll('button').find(b => b.text() === '确认覆盖').trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '确认添加').trigger('click')
  expect(wrapper.emitted('confirm')).toEqual([['replace'], ['append']])
  await wrapper.setProps({ applicationMode: 'replace', loading: true })
  expect(wrapper.text()).toContain('确认覆盖')
  expect(wrapper.findAll('button').find(b => b.text() === '确认覆盖').attributes('disabled')).toBeDefined()
})
