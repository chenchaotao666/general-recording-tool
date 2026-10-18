// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { smartSearchReplace } from '../src/api/index.js'
import { currentFindKey, findCellKey, findMatchKeys } from '../src/smart/utils/findReplace.js'
import FindReplaceDialog from '../src/components/smart/panels/FindReplaceDialog.vue'

vi.mock('../src/api/index.js', () => ({ smartSearchReplace: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

const DialogStub = defineComponent({
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dialog-stub"><slot /><slot name="footer" /></div>',
})

const textMatch = (overrides = {}) => ({
  recordId: 1, field: 'f_1', fieldLabel: '文本', fieldType: 'text', value: '台',
  replaceable: true, blockedReason: null, ...overrides,
})
const formulaMatch = (overrides = {}) => ({
  recordId: 2, field: 'f_2', fieldLabel: '公式', fieldType: 'formula', value: '台',
  replaceable: false, blockedReason: 'type', ...overrides,
})

function mountDialog() {
  return mount(FindReplaceDialog, {
    props: { visible: true, tableId: 7 },
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
