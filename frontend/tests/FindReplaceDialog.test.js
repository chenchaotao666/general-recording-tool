// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { smartSearchReplace } from '../src/api/index.js'
import { currentFindKey, findCellKey, findMatchKeys, orderFindMatches } from '../src/smart/utils/findReplace.js'
import FindReplaceDialog from '../src/components/smart/panels/FindReplaceDialog.vue'

vi.mock('../src/api/index.js', () => ({ smartSearchReplace: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

const DialogStub = defineComponent({
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dialog-stub el-dialog"><slot /><slot name="footer" /></div>',
})

const textMatch = (overrides = {}) => ({
  recordId: 1, field: 'f_1', fieldLabel: '文本', fieldType: 'text', value: '台',
  replaceable: true, blockedReason: null, ...overrides,
})
const formulaMatch = (overrides = {}) => ({
  recordId: 2, field: 'f_2', fieldLabel: '公式', fieldType: 'formula', value: '台',
  replaceable: false, blockedReason: 'type', ...overrides,
})

function mountDialog(props = {}) {
  return mount(FindReplaceDialog, {
    attachTo: document.body,
    props: { visible: true, tableId: 7, ...props },
    global: { stubs: { 'el-dialog': DialogStub } },
  })
}

function button(wrapper, text) {
  return wrapper.findAll('button').find(b => b.text() === text)
}

async function runFind(wrapper, value = '台') {
  const input = wrapper.find('.fr-find-input')
  await input.setValue(value)
  await input.trigger('keydown', { key: 'Enter' })
  await flushPromises()
}

beforeEach(() => {
  smartSearchReplace.mockReset()
})

describe('智能表查找替换面板', () => {
  test('收起/展开、结果计数、循环导航和高亮事件', async () => {
    const matches = [textMatch(), textMatch({ recordId: 2, field: 'f_3' })]
    smartSearchReplace.mockResolvedValue({ matches })
    const wrapper = mountDialog()
    expect(wrapper.find('.fr-title').text()).toBe('查找')
    expect(wrapper.find('.fr-expand').exists()).toBe(true)

    await runFind(wrapper)
    expect(smartSearchReplace).toHaveBeenCalledWith(7, { find: '台' })
    expect(wrapper.find('.fr-count').text()).toBe('1/2')
    expect(wrapper.emitted('locate')[0][0]).toEqual(matches[0])
    expect(wrapper.emitted('highlight').at(-1)[0].currentIndex).toBe(0)

    await wrapper.get('[aria-label="下一个"]').trigger('click')
    expect(wrapper.find('.fr-count').text()).toBe('2/2')
    await wrapper.get('[aria-label="下一个"]').trigger('click')
    expect(wrapper.find('.fr-count').text()).toBe('1/2')

    await wrapper.get('.fr-expand').trigger('click')
    expect(wrapper.find('.fr-title').text()).toBe('查找替换')
    expect(wrapper.find('#smart-find-replace').attributes('placeholder')).toBe('输入替换内容')
    expect(button(wrapper, '替换').attributes('disabled')).toBeUndefined()
    expect(button(wrapper, '全部替换').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  test('公式命中允许查找，但单个替换显示类型提示', async () => {
    smartSearchReplace.mockResolvedValue({ matches: [formulaMatch()] })
    const wrapper = mountDialog()
    await wrapper.get('.fr-expand').trigger('click')
    await runFind(wrapper)
    await button(wrapper, '替换').trigger('click')

    expect(wrapper.find('.fr-status').text()).toBe('无法替换 “公式” 类型')
    expect(smartSearchReplace).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  test('单个替换提交当前坐标、返回撤销变更并刷新匹配', async () => {
    const match = textMatch()
    const changes = [{ recordId: 1, field: 'f_1', before: '台', after: '台1' }]
    smartSearchReplace
      .mockResolvedValueOnce({ matches: [match] })
      .mockResolvedValueOnce({ changes, replacedCells: 1, skipped: 0 })
      .mockResolvedValueOnce({ matches: [] })
    const wrapper = mountDialog()
    await wrapper.get('.fr-expand').trigger('click')
    await runFind(wrapper)
    await wrapper.get('#smart-find-replace').setValue('台1')
    await button(wrapper, '替换').trigger('click')
    await flushPromises()

    expect(smartSearchReplace.mock.calls[1][1]).toEqual({
      find: '台', replace: '台1', replace_current: true, record_id: 1, field: 'f_1',
    })
    expect(wrapper.emitted('replaced')[0][0]).toEqual({ changes, label: '替换 1 处' })
    expect(smartSearchReplace).toHaveBeenCalledTimes(3)
    expect(wrapper.find('.fr-count').text()).toBe('0/0')
    wrapper.unmount()
  })

  test('全部替换需要确认，部分跳过时保留面板并显示提示', async () => {
    const changes = [{ recordId: 1, field: 'f_1', before: '台', after: '台1' }]
    smartSearchReplace
      .mockResolvedValueOnce({ matches: [textMatch(), formulaMatch()] })
      .mockResolvedValueOnce({ changes, replacedCells: 1, skipped: 1 })
      .mockResolvedValueOnce({ matches: [formulaMatch({ value: '台' })] })
    const wrapper = mountDialog()
    await wrapper.get('.fr-expand').trigger('click')
    await runFind(wrapper)
    await wrapper.get('#smart-find-replace').setValue('台1')
    await button(wrapper, '全部替换').trigger('click')

    expect(wrapper.find('.fr-confirm-text').text().replace(/\s+/g, ' ').trim())
      .toBe('确定将此智能表内的 2 处 “台” 全部替换为 “台1” 吗？')
    await button(wrapper, '确定').trigger('click')
    await flushPromises()

    expect(smartSearchReplace.mock.calls[1][1]).toEqual({ find: '台', replace: '台1', replace_all: true })
    expect(wrapper.emitted('replaced')[0][0]).toEqual({ changes, label: '全部替换 1 处' })
    expect(wrapper.find('.fr-status').text()).toBe('部分内容无法替换')
    expect(wrapper.find('.fr-title').text()).toBe('查找替换')
    wrapper.unmount()
  })

  test('关闭重开会清空旧查找状态', async () => {
    smartSearchReplace.mockResolvedValue({ matches: [textMatch()] })
    const wrapper = mountDialog()
    await runFind(wrapper)
    expect(wrapper.find('.fr-count').exists()).toBe(true)
    await wrapper.setProps({ visible: false })
    await wrapper.setProps({ visible: true })
    expect(wrapper.find('.fr-find-input').element.value).toBe('')
    expect(wrapper.find('.fr-count').exists()).toBe(false)
    expect(wrapper.find('.fr-title').text()).toBe('查找')
    wrapper.unmount()
  })
})

test('网格查找 key 与当前项计算稳定', () => {
  const matches = [textMatch(), formulaMatch()]
  expect(findCellKey(1, 'f_1')).toBe('1::f_1')
  expect(findMatchKeys(matches)).toEqual(new Set(['1::f_1', '2::f_2']))
  expect(currentFindKey(matches, 1)).toBe('2::f_2')
  expect(currentFindKey(matches, -1)).toBe('')
})


test('first search prefers the current page; repeated find advances and refresh still fetches', async () => {
  const matches = [textMatch(), textMatch({ recordId: 8 }), textMatch({ recordId: 9 })]
  smartSearchReplace.mockResolvedValue({ matches })
  const wrapper = mountDialog({ orderMatches: results => orderFindMatches(results, [{ id: 8 }, { id: 9 }], [{ field_name: 'f_1' }]) })
  await wrapper.get('.fr-expand').trigger('click')
  await wrapper.get('.fr-find-input').setValue('first')
  await button(wrapper, '\u67e5\u627e').trigger('click')
  await flushPromises()
  expect(wrapper.emitted('locate').at(-1)[0]).toEqual(matches[1])
  expect(wrapper.find('.fr-count').text()).toBe('1/3')
  await wrapper.get('[aria-label="\u4e0b\u4e00\u4e2a"]').trigger('click')
  expect(wrapper.find('.fr-count').text()).toBe('2/3')
  expect(wrapper.emitted('locate').at(-1)[0]).toEqual(matches[2])
  await wrapper.get('[aria-label="\u4e0a\u4e00\u4e2a"]').trigger('click')
  await button(wrapper, '\u67e5\u627e').trigger('click')
  expect(wrapper.emitted('locate').at(-1)[0]).toEqual(matches[2])
  await button(wrapper, '\u67e5\u627e').trigger('click')
  expect(wrapper.emitted('locate').at(-1)[0]).toEqual(matches[0])
  expect(smartSearchReplace).toHaveBeenCalledTimes(1)
  await wrapper.vm.refresh()
  expect(smartSearchReplace).toHaveBeenCalledTimes(2)
  await wrapper.get('.fr-find-input').setValue('second')
  await button(wrapper, '\u67e5\u627e').trigger('click')
  await flushPromises()
  expect(smartSearchReplace).toHaveBeenLastCalledWith(7, { find: 'second' })
  expect(wrapper.emitted('locate').at(-1)[0]).toEqual(matches[1])
  wrapper.unmount()
})

test('search falls back to first result when current page has no match', async () => {
  smartSearchReplace.mockResolvedValue({ matches: [textMatch()] })
  const wrapper = mountDialog({ orderMatches: results => orderFindMatches(results, [{ id: 99 }], [{ field_name: 'f_1' }]) })
  await runFind(wrapper)
  expect(wrapper.emitted('highlight').at(-1)[0].currentIndex).toBe(0)
  wrapper.unmount()
})


test('dragging the title moves the panel and stops on pointer release', async () => {
  const wrapper = mountDialog()
  const head = wrapper.get('.fr-head')
  head.element.setPointerCapture = vi.fn()
  wrapper.get('.el-dialog').element.getBoundingClientRect = () => ({ left: 100, top: 100, width: 400, height: 300 })
  await head.trigger('pointerdown', { button: 0, pointerId: 1, clientX: 120, clientY: 120 })
  await head.trigger('pointermove', { pointerId: 1, clientX: 200, clientY: 170 })
  expect(wrapper.get('.el-dialog').element.style.left).toBe('180px')
  expect(wrapper.get('.el-dialog').element.style.top).toBe('150px')
  await head.trigger('pointerup', { pointerId: 1 })
  await head.trigger('pointermove', { pointerId: 1, clientX: 300, clientY: 270 })
  expect(wrapper.get('.el-dialog').element.style.left).toBe('180px')
  await wrapper.setProps({ visible: false })
  await wrapper.setProps({ visible: true })
  expect(wrapper.get('.el-dialog').element.style.left).toBe('')
  wrapper.unmount()
})


test('matches follow displayed rows and columns before off-page or hidden results', () => {
  const matches = [
    textMatch({ recordId: 99 }), textMatch({ recordId: 2, field: 'b' }),
    textMatch({ recordId: 1, field: 'a' }), textMatch({ recordId: 2, field: 'a' }),
    textMatch({ recordId: 1, field: 'hidden' }), textMatch({ recordId: 1, field: 'b' }),
  ]
  const ordered = orderFindMatches(matches,
    [{ id: 99, __rowType: 'group' }, { id: 1 }, { id: 2 }],
    [{ field_name: 'b' }, { field_name: 'a' }])
  expect(ordered).toEqual([matches[5], matches[2], matches[1], matches[3], matches[0], matches[4]])
  expect(matches[0].recordId).toBe(99)
})


test('Enter keeps input focus while searching and advances again after the response', async () => {
  let resolveSearch
  smartSearchReplace.mockReturnValue(new Promise(resolve => { resolveSearch = resolve }))
  const wrapper = mountDialog({ viewId: 12 })
  const input = wrapper.get('.fr-find-input')
  await input.setValue('needle')
  input.element.focus()
  await input.trigger('keydown', { key: 'Enter' })
  expect(document.activeElement).toBe(input.element)
  expect(input.element.disabled).toBe(false)
  expect(input.element.readOnly).toBe(true)
  resolveSearch({ matches: [textMatch(), textMatch({ recordId: 2 })] })
  await flushPromises()
  expect(smartSearchReplace).toHaveBeenCalledWith(7, { find: 'needle', view_id: 12 })
  expect(document.activeElement).toBe(input.element)
  expect(input.element.readOnly).toBe(false)
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.find('.fr-count').text()).toBe('2/2')
  expect(smartSearchReplace).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})

test('starting on page two continues to page three then wraps to the top of page one', () => {
  const matches = [6, 5, 4, 3, 2, 1].map(recordId => textMatch({ recordId }))
  expect(orderFindMatches(matches, [{ id: 4 }, { id: 3 }], [{ field_name: 'f_1' }])
    .map(m => m.recordId)).toEqual([4, 3, 2, 1, 6, 5])
})
