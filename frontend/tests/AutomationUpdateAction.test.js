// @vitest-environment jsdom
import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, test, vi } from 'vitest'
import AutomationEditor from '../src/components/smart/automation/AutomationEditor.vue'
import ValueInput from '../src/components/smart/automation/ValueInput.vue'
import VarMenu from '../src/components/smart/automation/VarMenu.vue'
import DateValueInput from '../src/components/smart/automation/DateValueInput.vue'
import TbFieldSelect from '../src/components/smart/panels/TbFieldSelect.vue'
import { defineComponent, ref } from 'vue'

const popover = { name: 'ElPopover', template: '<div><slot name="reference" /><slot /></div>' }
const fields = [{ field_name: 'f_1', label: '产品', field_type: 'singleSelect', options: {
  options: [{ id: 'a', label: '产品 A', color: 'blue' }, { id: 'b', label: '产品 B', color: 'green' }],
} }]

test('step fields use the shared grouped picker and retain the variable descriptor', async () => {
  const variable = { kind: 'step', step: 1, key: 'field', field: 'f_1' }
  const wrapper = mount(VarMenu, { props: { inline: true, valueMode: true, hideTime: true,
    steps: [{ step: 1, name: '新增记录', columnGroups: [{ id: 'g1', name: '基本信息', field_names: ['f_1'] }],
      vars: [{ key: 'f_1', label: '产品', icon: 'singleSelect', var: variable }] }] },
    global: { plugins: [ElementPlus] } })
  await wrapper.find('.has-sub').trigger('mouseenter')
  expect(new DOMWrapper(document.body).find('.fpl-title').text()).toBe('选择字段')
  expect(wrapper.find('.fpl-group').text()).toBe('基本信息')
  await wrapper.find('.fpl-item.sub').trigger('click')
  expect(wrapper.emitted('pick')[0]).toEqual([variable, '第1步新增记录的 产品'])
  wrapper.unmount()
})

test('shared field selector toggles multiple fields and clears to an empty array', async () => {
  const wrapper = mount(TbFieldSelect, { props: { fields, modelValue: [], clearable: true,
    'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }) },
    global: { plugins: [ElementPlus], stubs: { ElPopover: popover } } })
  await wrapper.find('.fpl-item').trigger('click')
  expect(wrapper.props('modelValue')).toEqual(['f_1'])
  await wrapper.find('.fpl-item').trigger('click')
  expect(wrapper.props('modelValue')).toEqual([])
  await wrapper.find('.fpl-item').trigger('click')
  await wrapper.find('.tbfs-clear').trigger('click')
  expect(wrapper.props('modelValue')).toEqual([])
  wrapper.unmount()
})

test('step submenu moves up to stay inside the viewport near the bottom', async () => {
  const anchorTop = window.innerHeight - 50
  const measure = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function () {
    if (this.classList.contains('vm-sub')) return { top: anchorTop - 6, left: 376, right: 596, bottom: anchorTop + 294, width: 220, height: 300 }
    return { top: anchorTop, left: 600, right: 820, bottom: anchorTop + 40, width: 220, height: 40 }
  })
  const wrapper = mount(VarMenu, { props: { inline: true, valueMode: true, hideTime: true,
    steps: [{ step: 1, name: '新增记录', vars: [] }] }, global: { plugins: [ElementPlus] } })
  try {
    await wrapper.find('.has-sub').trigger('mouseenter')
    await flushPromises()
    const panel = wrapper.find('.vm-sub').element
    expect(parseFloat(panel.style.top)).toBeLessThan(-6)
    expect(anchorTop + parseFloat(panel.style.top) + 300).toBeLessThanOrEqual(window.innerHeight - 12)
    expect(panel.style.maxHeight).toBe('320px')
  } finally {
    wrapper.unmount()
    measure.mockRestore()
  }
})

test('date step submenu starts collapsed each time the dropdown opens', async () => {
  const wrapper = mount(DateValueInput, {
    props: { field: { field_type: 'date' }, steps: [{ step: 1, name: '新增记录', vars: [] }] },
    global: { plugins: [ElementPlus], stubs: { ElPopover: popover } },
  })
  const dropdown = wrapper.findComponent({ name: 'ElPopover' })
  dropdown.vm.$emit('update:visible', true)
  await flushPromises()
  expect(wrapper.find('.vm-sub').exists()).toBe(false)
  await wrapper.find('.vm-item.has-sub').trigger('mouseenter')
  expect(wrapper.find('.vm-sub').exists()).toBe(true)
  dropdown.vm.$emit('update:visible', false)
  await flushPromises()
  dropdown.vm.$emit('update:visible', true)
  await flushPromises()
  expect(wrapper.find('.vm-sub').exists()).toBe(false)
  wrapper.unmount()
})

test('step submenu closes on leave and stays open while crossing into its fields', async () => {
  vi.useFakeTimers()
  const wrapper = mount(VarMenu, { props: { valueMode: true, hideTime: true,
    steps: [{ step: 1, name: '新增记录', vars: [] }] }, global: { plugins: [ElementPlus] } })
  try {
    const row = wrapper.find('.has-sub')
    await row.trigger('mouseenter')
    await row.trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(40)
    await row.trigger('mouseenter')
    await vi.advanceTimersByTimeAsync(100)
    expect(wrapper.find('.vm-sub').exists()).toBe(true)
    await row.trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(80)
    expect(wrapper.find('.vm-sub').exists()).toBe(false)
  } finally {
    wrapper.unmount()
    vi.useRealTimers()
  }
})

test('date assignments only offer date fields and step time variables', async () => {
  const wrapper = mount(DateValueInput, {
    props: { field: { field_type: 'date' }, steps: [{ step: 1, name: '新增记录',
      vars: ['text', 'date', 'createdTime', 'lastModifiedTime', 'number', 'member'].map(icon => ({
        key: icon, label: icon, icon, var: { kind: 'step', step: 1, key: 'field', field: icon },
      })) }] },
    global: { plugins: [ElementPlus], stubs: { ElPopover: popover } },
  })
  wrapper.findComponent({ name: 'ElPopover' }).vm.$emit('update:visible', true)
  await flushPromises()
  await wrapper.find('.has-sub').trigger('mouseenter')
  expect(wrapper.findAll('.fpl-item').map(row => row.text())).toEqual(['date', 'createdTime', 'lastModifiedTime'])
  await wrapper.findAll('.fpl-item')[0].trigger('click')
  expect(wrapper.emitted('update:modelValue')[0][0].var.field).toBe('date')
  wrapper.unmount()
})

test('create record config switches between specified content and blank records', async () => {
  const wrapper = mount(AutomationEditor, {
    props: { tableId: 1, fields, tables: [], loadFields: async () => fields,
      modelValue: { name: '新增', trigger: { type: 'recordCreated', filter: { conditions: [] } },
        actions: [{ id: 'new1', type: 'createRecord', tableId: 1, recordMode: 'specified', values: [] }] },
      'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }) },
    global: { plugins: [ElementPlus], stubs: { ElPopover: popover } },
  })
  expect(wrapper.find('.ae-create-trigger').text()).toBe('指定内容的记录0')
  await wrapper.find('.ae-create-values > button').trigger('click')
  expect(wrapper.props('modelValue').actions[0].values).toHaveLength(1)
  expect(wrapper.find('.ae-create-trigger .ae-config-count').text()).toBe('1')
  await wrapper.findAll('.ae-create-options input')[0].setValue(true)
  expect(wrapper.props('modelValue').actions[0]).toMatchObject({ recordMode: 'blank', values: [] })
  expect(wrapper.find('.ae-create-values').exists()).toBe(false)
  expect(wrapper.find('.ae-create-trigger').text()).toBe('空白记录')
  await wrapper.findAll('.ae-create-options input')[1].setValue(true)
  expect(wrapper.find('.ae-create-values').exists()).toBe(true)
  wrapper.unmount()
})

test('update action range, match mode and assigned fields preserve the saved schema', async () => {
  const wrapper = mount(AutomationEditor, {
    props: {
      tableId: 1, fields, tables: [{ id: 1, label: '客户' }], loadFields: async () => fields,
      modelValue: { name: '修改', trigger: { type: 'recordCreated', filter: { conditions: [] } },
        actions: [{ id: 'a1', type: 'updateRecords', tableId: 1, target: 'triggered', match: 'all', conditions: [], values: [] }] },
      'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }),
    },
    global: { plugins: [ElementPlus], stubs: { ElPopover: popover } },
  })
  await wrapper.findAll('.ae-target-option input')[1].setValue(true)
  expect(wrapper.props('modelValue').actions[0].target).toBe('matching')
  await wrapper.find('.ae-target-conditions button').trigger('click')
  expect(wrapper.props('modelValue').actions[0].conditions).toHaveLength(1)
  const match = wrapper.find('.ae-target-conditions').findComponent({ name: 'ElSelect' })
  match.vm.$emit('update:modelValue', 'any')
  await flushPromises()
  expect(wrapper.props('modelValue').actions[0].match).toBe('any')
  await wrapper.find('.ae-update-values > button').trigger('click')
  expect(wrapper.props('modelValue').actions[0].values).toHaveLength(1)
  await wrapper.find('.ae-update-values .ae-create-delete').trigger('click')
  expect(wrapper.props('modelValue').actions[0].values).toHaveLength(0)
  wrapper.unmount()
})

test('enum assignments support static choices, multiselect and step variables', async () => {
  const wrapper = mount(ValueInput, {
    props: { field: fields[0], 'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }) },
    global: { plugins: [ElementPlus], stubs: { ElPopover: popover } },
  })
  await wrapper.findAll('.vi-option-row')[0].trigger('click')
  expect(wrapper.props('modelValue')).toEqual({ type: 'static', value: 'a' })
  await wrapper.setProps({ field: { ...fields[0], field_type: 'multiSelect' }, modelValue: { type: 'static', value: ['a'] } })
  await wrapper.findAll('.vi-option-row')[1].trigger('click')
  expect(wrapper.props('modelValue').value).toEqual(['a', 'b'])
  await wrapper.findAll('.vi-option-row')[0].trigger('click')
  expect(wrapper.props('modelValue').value).toEqual(['b'])
  wrapper.findComponent(VarMenu).vm.$emit('pick', { kind: 'step', step: 1, key: 'field', field: 'f_1' }, '第1步的产品')
  await flushPromises()
  expect(wrapper.props('modelValue').type).toBe('var')
  expect(wrapper.find('.vi-chip').text()).toContain('第1步的产品')
  wrapper.unmount()
})

test.each(['text', 'date'])('picking natural time for %s keeps the specified-content popover open', async fieldType => {
  const host = defineComponent({
    components: { ValueInput },
    setup() {
      return { open: ref(true), value: ref(undefined), field: { field_name: 'field', field_type: fieldType, options: {} } }
    },
    template: `<el-popover v-model:visible="open" trigger="click" :hide-after="0">
      <template #reference><button>指定内容</button></template>
      <ValueInput v-model="value" :field="field" />
    </el-popover>`,
  })
  const wrapper = mount(host, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  await flushPromises()
  const variableButton = document.querySelector(fieldType === 'date' ? '.dvi-trigger' : '.vi-var')
  variableButton.click()
  await flushPromises()
  if (fieldType !== 'date') {
    const naturalTime = document.querySelector('.vi-vars-pop .vm-item')
    naturalTime.dispatchEvent(new MouseEvent('mouseenter'))
    await flushPromises()
  }
  const today = document.querySelector(fieldType === 'date' ? '.dvi-days .dvi-item' : '.vi-vars-pop .vm-sub .vm-item')
  today.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  today.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  today.click()
  await flushPromises()
  expect(wrapper.vm.value).toEqual({ type: 'var', var: { kind: 'time', key: 'today' }, label: '今天' })
  expect(wrapper.vm.open).toBe(true)
  document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  document.body.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  document.body.click()
  await new Promise(resolve => setTimeout(resolve, 20))
  await flushPromises()
  expect(wrapper.vm.open).toBe(false)
  wrapper.unmount()
})
