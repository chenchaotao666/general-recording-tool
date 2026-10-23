// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeAll, expect, test } from 'vitest'
import { nextTick, ref } from 'vue'
import ElementPlus from 'element-plus'
import ConditionValue from '../src/components/smart/panels/ConditionValue.vue'
import FilterPanel from '../src/components/smart/panels/FilterPanel.vue'
import FillPanel from '../src/components/smart/panels/FillPanel.vue'
import SortPanel from '../src/components/smart/panels/SortPanel.vue'
import GroupPanel from '../src/components/smart/panels/GroupPanel.vue'

beforeAll(() => {
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
})
const wrappers = []
afterEach(() => {
  wrappers.splice(0).forEach(w => w.unmount())
  document.body.innerHTML = ''
})
const fields = [
  { field_name: 'status', label: '状态', field_type: 'multiSelect', options: { options: [
    { id: 'a', label: 'Alpha' }, { id: 'b', label: 'Beta' },
  ] } },
  { field_name: 'date', label: '日期', field_type: 'date' },
]
function render(component, props, provide = {}) {
  const w = mount(component, { attachTo: document.body, props,
    slots: { default: '<button>面板</button>' }, global: { plugins: [ElementPlus], provide } })
  wrappers.push(w)
  return w
}
async function settle() {
  await flushPromises()
  await new Promise(resolve => setTimeout(resolve, 30))
  await nextTick()
}
async function click(el) {
  expect(el).toBeTruthy()
  el.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
  el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  el.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }))
  await settle()
}
function visible(selector) {
  return [...document.querySelectorAll(selector)].find(el => !el.closest('[aria-hidden="true"], [style*="display: none"]'))
}

for (const [component, prop, rule] of [
  [FillPanel, 'rules', { id: 'r', fieldId: 'status', fillTarget: 'all' }],
  [SortPanel, 'sorts', { fieldId: 'status', direction: 'asc' }],
  [GroupPanel, 'groups', { fieldId: 'status', direction: 'asc' }],
]) {
  test(`${component.__name} keeps its parent open when a body field menu is selected`, async () => {
    const w = render(component, { visible: true, fields, [prop]: [rule] })
    await settle()
    await click(visible('.tbfs'))
    const list = visible('.fpl')
    expect(list).toBeTruthy()
    expect(list.closest('.flp, .sp, .gp')).toBeNull()
    await click([...list.querySelectorAll('.fpl-item')].find(el => el.textContent.includes('日期')))
    expect(w.emitted('update:visible')).toBeUndefined()
    expect(visible('.tbfs').textContent).toContain('日期')
    await w.setProps({ visible: false })
    await settle()
    expect(visible('.fpl')).toBeUndefined()
  })
}

test('filter field, operator and date mode menus are body children and preserve the parent', async () => {
  const w = render(FilterPanel, { visible: true, fields })
  await settle()
  await click(visible('.tbp-add'))
  const list = visible('.fpl')
  expect(list.closest('.fp')).toBeNull()
  await click([...list.querySelectorAll('.fpl-item')].find(el => el.textContent.includes('日期')))
  await click(visible('.fp-op'))
  const opMenu = visible('.fp-op-pop')
  expect(opMenu.closest('.fp')).toBeNull()
  await click(opMenu.querySelector('.el-dropdown-menu__item'))
  await click(visible('.dv-mode .el-select__wrapper'))
  const mode = visible('.dv-mode-pop')
  expect(mode.closest('.fp')).toBeNull()
  await click([...mode.querySelectorAll('.el-select-dropdown__item')].find(el => el.textContent.includes('今天')))
  expect(w.emitted('update:visible')).toBeUndefined()
  expect(visible('.dv-mode').textContent).toContain('今天')
})

for (const member of [false, true]) {
  test(`condition ${member ? 'member' : 'enum'} body menu preserves search, multiple selection and removal`, async () => {
    const w = render(ConditionValue, { field: member ? { field_name: 'people', field_type: 'member' } : fields[0], value: [] },
      { smartMembers: ref([{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }]) })
    await click(w.find('.enum-val').element)
    const pop = visible('.ev-pop')
    expect(w.element.contains(pop)).toBe(false)
    const input = pop.querySelector('input')
    input.value = 'Beta'; input.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    expect(pop.querySelectorAll('.ev-item')).toHaveLength(1)
    await click(pop.querySelector('.ev-item'))
    expect(w.emitted('update').at(-1)).toEqual([['b']])
    expect(visible('.ev-pop')).toBeTruthy()
    await click(w.find('.smt-close').element)
    expect(w.emitted('update').at(-1)).toEqual([[]])
    await click(document.body)
    expect(visible('.ev-pop')).toBeUndefined()
  })
}

test('fill palette escapes the scroll area and keeps color plus whole-row changes interactive', async () => {
  const w = render(FillPanel, { visible: true, fields, rules: [{ id: 'r', fieldId: 'status', fillTarget: 'all' }] })
  await settle()
  await click(visible('.flp-color'))
  const palette = visible('.flp-pal')
  expect(palette.closest('.flp-scroll')).toBeNull()
  await click(palette.querySelector('.flp-cell'))
  await click(palette.querySelector('.el-checkbox__input'))
  await new Promise(resolve => setTimeout(resolve, 280))
  expect(w.emitted('change').at(-1)[0][0]).toMatchObject({ color: expect.any(String), wholeRow: true })
  expect(w.emitted('update:visible')).toBeUndefined()
  expect(visible('.flp-pal')).toBeTruthy()
  await w.setProps({ visible: false })
  await settle()
  expect(visible('.flp-pal')).toBeUndefined()
})
