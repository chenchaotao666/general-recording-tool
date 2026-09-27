// @vitest-environment jsdom
// 回归：去重/逐条处理的「记录列表」变量选择器必须列出列表型变量（records/groups），
// 曾经因正则没算结尾大括号（{nodes.q_1.records} 以 } 结尾）永远过滤为空
import { flushPromises, mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import ElementPlus from 'element-plus'
import SchemaForm from '../src/components/workflow/SchemaForm.vue'

const schema = {
  required: ['records'],
  properties: { records: { type: 'string', format: 'template', title: '记录列表' } },
}

const vars = [
  {
    title: '查询 (q_1)',
    items: [
      { label: '记录数', expr: '{nodes.q_1.count}' },
      { label: '记录列表', expr: '{nodes.q_1.records}' },
      { label: '第一条·ID', expr: '{nodes.q_1.records.0.id}' },
    ],
  },
  { title: '时间变量（内置）', items: [{ label: '今天', expr: '{now.today}' }] },
]

test('记录列表是下拉框：列表型变量可见，标量被过滤', async () => {
  const wrapper = mount(SchemaForm, {
    props: { schema, modelValue: {}, nodeType: 'dedupe', vars },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()

  // 字段是 el-select 下拉
  const sel = wrapper.find('.el-select')
  expect(sel.exists()).toBe(true)
  await sel.trigger('click')
  await flushPromises()

  // 下拉选项（teleport 到 body）：{nodes.q_1.records} 可见，标量不出现
  const options = [...document.querySelectorAll('.el-select-dropdown__item')].map((x) => x.textContent)
  expect(options.some((t) => t.includes('记录列表'))).toBe(true)
  expect(options.some((t) => t.includes('记录数'))).toBe(false)
  expect(options.some((t) => t.includes('第一条·ID'))).toBe(false)
  wrapper.unmount()
})

test('条件分支的「判断对象」自动填充：循环体内优先选当前条目（item）', async () => {
  const condSchema = {
    required: ['record'],
    properties: { record: { type: 'string', title: '判断对象' } },
  }
  const loopVars = [
    { title: '触发器', items: [{ label: '触发记录（整体）', expr: '{trigger.record}' }] },
    {
      title: '逐条处理 (loop_1)',
      items: [
        { label: '当前条目（整体）', expr: '{nodes.loop_1.item}' },
        { label: '当前序号（从 0 起）', expr: '{nodes.loop_1.index}' },
      ],
    },
  ]
  const wrapper = mount(SchemaForm, {
    props: { schema: condSchema, modelValue: {}, nodeType: 'condition', vars: loopVars },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  // 自动填充应选「当前条目」而不是触发记录
  const events = wrapper.emitted('update:modelValue') || []
  const last = events.at(-1)?.[0] || {}
  expect(last.record).toBe('{nodes.loop_1.item}')
  wrapper.unmount()
})
