// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { test, expect, vi } from 'vitest'
import ElementPlus from 'element-plus'
import RecordDetailPanel from '../src/components/smart/panels/RecordDetailPanel.vue'
import RecordDetailFloating from '../src/components/smart/panels/RecordDetailFloating.vue'
import RecordDetailContent from '../src/components/smart/panels/RecordDetailContent.vue'
import SmartCellEditor from '../src/components/smart/grid/SmartCellEditor.vue'
import LinkCellPanel from '../src/components/smart/grid/LinkCellPanel.vue'
import FileCellPanel from '../src/components/smart/grid/FileCellPanel.vue'
import ImageCellPanel from '../src/components/smart/grid/ImageCellPanel.vue'
import RelationCellPanel from '../src/components/smart/grid/RelationCellPanel.vue'
vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
for (const component of [RecordDetailPanel, RecordDetailFloating]) {
  test(`${component.__name} shares content and forwards edits, permissions and navigation`, async () => {
    const commit = vi.fn(), nav = vi.fn()
    const field = { id: 1, field_name: 'title', field_type: 'text', label: 'Title' }
    const wrapper = mount(component, { props: { visible: true, source: 'Source', record: { id: 1, title: 'Original' }, fields: [field], hasNext: true, canCreate: false, canDelete: false, onCellCommit: commit, onNav: nav }, global: { plugins: [ElementPlus], stubs: { teleport: true } } })
    expect(wrapper.findComponent(RecordDetailContent).exists()).toBe(true)
    await wrapper.find('.rd-value').trigger('click')
    await wrapper.find('textarea').setValue('Updated')
    await wrapper.find('textarea').trigger('blur')
    expect(commit).toHaveBeenCalledWith({ row: { id: 1, title: 'Original' }, field, value: 'Updated' })
    const buttons = wrapper.findAll('button').filter(b => b.attributes('aria-label') === '下一条')
    await buttons[0].trigger('click')
    expect(nav).toHaveBeenCalledWith(1)
    await wrapper.setProps({ readonly: true, record: { id: 2, title: 'Second' } })
    expect(wrapper.find('.rd-title').text()).toBe('Second')
    expect(wrapper.find('.rd-value').classes()).not.toContain('editable')
    wrapper.unmount()
  })
}

test('AI text uses its output editor and still obeys cell permissions', async () => {
  const field = { field_name: 'ai', field_type: 'ai', label: 'AI', options: { outputType: 'text' } }
  const wrapper = mount(RecordDetailContent, { props: { record: { id: 1, ai: 'Generated' }, fields: [field], canCreate: false, canDelete: false }, global: { plugins: [ElementPlus] } })
  try {
    await wrapper.find('.rd-value').trigger('click')
    await wrapper.find('textarea').setValue('Manual correction')
    await wrapper.find('textarea').trigger('blur')
    expect(wrapper.emitted('cell-commit')[0][0]).toMatchObject({ field, value: 'Manual correction' })
    await wrapper.setProps({ canEditCell: () => false })
    expect(wrapper.find('.rd-value').classes()).not.toContain('editable')
  } finally { wrapper.unmount() }
})

test('progress editor remains mounted until blur can commit its draft', async () => {
  const field = { field_name: 'progress', field_type: 'progress', label: 'Progress', options: {} }
  const wrapper = mount(RecordDetailContent, { attachTo: document.body, props: { record: { id: 1, progress: 20 }, fields: [field], canCreate: false, canDelete: false }, global: { plugins: [ElementPlus] } })
  try {
    await wrapper.find('.rd-value').trigger('click')
    expect(wrapper.find('.rd-value').classes()).toContain('keep-pad')
    await wrapper.find('input').setValue('65')
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(wrapper.findComponent(SmartCellEditor).exists()).toBe(true)
    await wrapper.find('input').trigger('blur')
    expect(wrapper.emitted('cell-commit')[0][0]).toMatchObject({ field, value: 65 })
  } finally { wrapper.unmount() }
})

test('detail progress supports dragging without opening the numeric editor', async () => {
  const field = { field_name: 'progress', field_type: 'progress', label: 'Progress', options: {} }
  const wrapper = mount(RecordDetailContent, { props: { record: { id: 1, progress: 20 }, fields: [field], canCreate: false, canDelete: false }, global: { plugins: [ElementPlus] } })
  try {
    const slider = wrapper.find('.progress-slider')
    slider.element.value = '65'
    await slider.trigger('input')
    expect(wrapper.emitted('cell-commit')).toBeUndefined()
    await slider.trigger('change')
    await slider.trigger('click')
    expect(wrapper.emitted('cell-commit')[0][0]).toMatchObject({ field, value: 65 })
    expect(wrapper.findComponent(SmartCellEditor).exists()).toBe(false)
    await wrapper.setProps({ readonly: true })
    expect(wrapper.find('.progress-slider').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

test('scrolling record details dismisses the read-only field hint', async () => {
  const wrapper = mount(RecordDetailContent, {
    props: { record: { id: 1, serial: 134 }, fields: [{ field_name: 'serial', field_type: 'autoNumber', label: 'Serial' }], canCreate: false, canDelete: false },
    global: { plugins: [ElementPlus], stubs: { teleport: true } },
  })
  try {
    await wrapper.find('.rd-value').trigger('click')
    expect(wrapper.find('.rd-blocked-hint').exists()).toBe(true)
    await wrapper.find('.rd-body').trigger('scroll')
    expect(wrapper.find('.rd-blocked-hint').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

test('detail scroll closes a persistent link panel without unmounting its content', async () => {
  const wrapper = mount(RecordDetailContent, {
    attachTo: document.body,
    props: { record: { id: 1, url: { text: 'Example', url: 'https://example.com' } }, fields: [{ field_name: 'url', field_type: 'url', label: 'Link' }], canCreate: false, canDelete: false },
    global: { plugins: [ElementPlus] },
  })
  try {
    const panel = wrapper.findComponent(LinkCellPanel)
    await panel.vm.focus()
    expect(panel.find('.cell-dropdown').attributes('aria-expanded')).toBe('true')
    await wrapper.find('.rd-body').trigger('scroll')
    expect(panel.find('.cell-dropdown').attributes('aria-expanded')).toBe('false')
    expect(wrapper.findComponent(LinkCellPanel).exists()).toBe(true)
    expect(wrapper.emitted('cell-commit')).toBeUndefined()
  } finally { wrapper.unmount() }
})

test.each([['url', LinkCellPanel], ['file', FileCellPanel], ['image', ImageCellPanel], ['relation', RelationCellPanel]])('%s keeps the same detail content while its panel opens and closes', async (type, component) => {
  const field = { field_name: 'media', field_type: type, label: 'Media' }
  const wrapper = mount(RecordDetailContent, {
    props: { record: { id: 1, media: type === 'url' ? { text: 'Example', url: 'https://example.com' } : [] }, fields: [field], canCreate: false, canDelete: false },
    global: { plugins: [ElementPlus] },
  })
  try {
    const panel = wrapper.findComponent(component)
    const instance = panel.vm.$.uid
    panel.vm.$emit('open')
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(component).vm.$.uid).toBe(instance)
    expect(wrapper.find('.rd-value').classes()).toContain('keep-pad')
    panel.vm.$emit('collapse')
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(component).vm.$.uid).toBe(instance)
    await wrapper.setProps({ readonly: true })
    expect(wrapper.findComponent(component).props('readonly')).toBe(true)
  } finally { wrapper.unmount() }
})

test('hidden view fields are excluded from details and title choices, including live changes', async () => {
  const fields = ['hidden', 'shown'].map(field_name => ({ field_name, label: field_name, field_type: 'text' }))
  const wrapper = mount(RecordDetailContent, {
    props: { record: { id: 1, hidden: 'Secret', shown: 'Visible title' }, fields, titleField: 'hidden', canSetTitle: true,
      canCreate: false, canDelete: false, view: { config: { fieldVisibility: { hidden: false } } },
      columnGroups: [{ id: 1, name: 'Hidden group', field_names: ['hidden'] }] },
    global: { plugins: [ElementPlus], stubs: { teleport: true, ElPopover: { template: '<div><slot name="reference"/><slot/></div>' } } },
  })
  try {
    expect(wrapper.findAll('.rd-label > span:last-child').map(el => el.text())).toEqual(['shown'])
    expect(wrapper.find('.rd-title-trigger').text()).toContain('Visible title')
    expect(wrapper.find('.rd-group').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'FieldPickList' }).props('fields').map(f => f.field_name)).toEqual(['shown'])
    await wrapper.setProps({ view: { config: { fieldVisibility: { shown: false } } } })
    expect(wrapper.findAll('.rd-label > span:last-child').map(el => el.text())).toEqual(['hidden'])
    expect(wrapper.find('.rd-title-trigger').text()).toContain('Secret')
    expect(wrapper.findComponent({ name: 'FieldPickList' }).props('fields').map(f => f.field_name)).toEqual(['hidden'])
    await wrapper.setProps({ view: { config: { fieldVisibility: { shown: false, hidden: false } } } })
    expect(wrapper.findAll('.rd-row')).toHaveLength(0)
    expect(wrapper.findComponent({ name: 'FieldPickList' }).props('fields')).toEqual([])
  } finally { wrapper.unmount() }
})
