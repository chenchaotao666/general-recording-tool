// @vitest-environment jsdom
// 复现「点击添加节点时报错 Cannot set properties of null (setting __vnode)」
// 运行：npx vitest run tests/WorkflowEditor.addnode.test.js
import { flushPromises, mount } from '@vue/test-utils'
import { beforeAll, expect, vi, test } from 'vitest'
import ElementPlus from 'element-plus'

// ---- mock api 层 ----
vi.mock('../src/api', () => ({
  listTables: vi.fn(async () => []),
  listProviders: vi.fn(async () => []),
  listWorkflows: vi.fn(async () => []),
  getTable: vi.fn(async () => ({ fields: [] })),
  getWorkflow: vi.fn(async () => ({})),
  getWorkflowRun: vi.fn(async () => ({ node_runs: [] })),
  checkWorkflow: vi.fn(async () => ({ issues: [] })),
  createWorkflow: vi.fn(async () => ({ id: 1 })),
  updateWorkflow: vi.fn(async () => ({ id: 1 })),
  runWorkflow: vi.fn(async () => ({})),
  testRunWorkflow: vi.fn(async () => ({})),
  workflowRuns: vi.fn(async () => []),
  workflowNodeTypes: vi.fn(async () => [
    { type: 'send_message', name: '发送通知', category: 'action', description: '', config_schema: { properties: { channel: { type: 'string', enum: ['notify'] }, template: { type: 'string', format: 'template' } }, required: ['channel', 'template'] } },
    { type: 'condition', name: '条件分支', category: 'logic', description: '', config_schema: { properties: { record: { type: 'string' }, rules: { type: 'array' }, logic: { type: 'string', enum: ['AND', 'OR'], default: 'AND' } }, required: ['record'] } },
    { type: 'http_request', name: 'HTTP 请求', category: 'action', description: '', config_schema: { properties: { url: { type: 'string' }, headers: { type: 'object' }, body: { type: 'object' }, timeout_seconds: { type: 'integer', default: 30 } }, required: ['url'] } },
    { type: 'sub_workflow', name: '子流程调用', category: 'action', description: '', config_schema: { properties: { workflow_id: { type: 'integer', format: 'workflow-ref' }, params: { type: 'object' } }, required: ['workflow_id'] } },
    { type: 'approval', name: '人工审批', category: 'human', description: '', config_schema: { properties: { title: { type: 'string' }, detail_template: { type: 'string', format: 'template' } }, required: ['title'] } },
    { type: 'llm_transform', name: 'LLM 处理', category: 'ai', description: '', config_schema: { properties: { prompt: { type: 'string', format: 'template' }, output_format: { type: 'string', enum: ['text', 'json'], default: 'text' }, output_keys: { type: 'array' } }, required: ['prompt'] } },
  ]),
}))

// ---- mock vue-router（routeState 可变：支持带 id 打开已有工作流的用例） ----
const routeState = vi.hoisted(() => ({ params: {}, query: {} }))
vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

beforeAll(() => {
  // jsdom 没有 ResizeObserver / matchMedia / SVG 尺寸 API
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }))
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 })
  // vue-flow 需要非零容器尺寸才会真正渲染节点
  Object.defineProperty(window.HTMLElement.prototype, 'offsetWidth', { configurable: true, get() { return 800 } })
  Object.defineProperty(window.HTMLElement.prototype, 'offsetHeight', { configurable: true, get() { return 600 } })
  window.HTMLElement.prototype.getBoundingClientRect = function () {
    return { x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }
  }
  // d3-zoom 需要
  global.DOMMatrixReadOnly = global.DOMMatrixReadOnly || class { constructor() {} }
})

import WorkflowEditor from '../src/views/WorkflowEditor.vue'

test('点击节点面板添加节点不抛错', async () => {
  const errors = []
  const wrapper = mount(WorkflowEditor, {
    global: {
      // el-table 在 jsdom 下会以无上下文调用列插槽（非本次复现目标），打桩掉
      stubs: { 'el-table': true, 'el-table-column': true },
      config: {
        errorHandler: (e) => errors.push(e),
        warnHandler: (msg) => { if (/Unhandled error/.test(msg)) errors.push(new Error(msg)) },
      },
    },
    attachTo: document.body,
  })
  await flushPromises()

  // 捕获 promise 级错误
  const rejections = []
  const onRej = (e) => rejections.push(e.reason)
  window.addEventListener('unhandledrejection', onRej)

  const items = wrapper.findAll('.palette-item')
  expect(items.length).toBeGreaterThan(0)
  for (const item of items) {
    await item.trigger('click')
    await flushPromises()
  }

  // 叠加场景：打开过抽屉（el-drawer 是 teleport 组件）后再添加节点
  const checkBtn = wrapper.findAll('button').find((b) => (b.text() || '').includes('检查问题'))
  await checkBtn?.trigger('click')
  await flushPromises()
  await items[0].trigger('click')
  await flushPromises()

  window.removeEventListener('unhandledrejection', onRej)
  expect(rejections.map(String)).toEqual([])
  expect(errors.map(String)).toEqual([])
  wrapper.unmount()
})

test('条件分支的条件规则字段跟随判断对象（审批整体输出 → approved/comment）', async () => {
  const { getWorkflow, getTable } = await import('../src/api')
  getWorkflow.mockResolvedValue({
    id: 5, name: '审批流', enabled: false,
    trigger: { type: 'record_created', table_id: 1 },
    nodes: [
      { id: 'a_1', type: 'approval', name: '人工审批', config: { title: '审批' } },
      { id: 'c_1', type: 'condition', name: '通过？', config: { record: '{nodes.a_1}', rules: [{ field: '', op: 'eq', value: '' }] } },
    ],
    edges: [{ from: 'a_1', to: 'c_1' }],
  })
  getTable.mockResolvedValue({ fields: [{ field_name: 'title', label: '报销事项', data_type: 'varchar' }] })
  routeState.params = { id: '5' }
  routeState.query = {}

  const wrapper = mount(WorkflowEditor, {
    global: {
      plugins: [ElementPlus],
      stubs: { 'el-table': true, 'el-table-column': true },
    },
    attachTo: document.body,
  })
  await flushPromises()
  await new Promise((r) => setTimeout(r, 50))

  // 点开条件分支节点
  const node = wrapper.findAll('.flow-node').find((n) => n.text().includes('通过'))
  expect(node).toBeTruthy()
  await node.trigger('click')
  await flushPromises()

  // 条件规则的字段是自由输入框 + ⚡（与多路分支的 cases 一致），⚡ 面板列出判断对象的键
  const row = wrapper.find('.filters-editor .rule-row')
  expect(row.exists()).toBe(true)
  expect(row.find('.f.el-select').exists()).toBe(false)   // 字段控件不是表字段下拉
  expect(row.find('.f.el-input').exists()).toBe(true)     // 是自由输入框
  await row.find('.picker-btn').trigger('click')
  await flushPromises()
  const pickerText = [...document.querySelectorAll('.el-popover .v-item, .el-popover .g-title')]
    .map((x) => x.textContent).join('\n')
  expect(pickerText).toContain('判断对象的字段')   // 分组标题正确
  expect(pickerText).toContain('是否通过')        // 判断对象（审批输出）的键在其中
  wrapper.unmount()
  routeState.params = {}
})
