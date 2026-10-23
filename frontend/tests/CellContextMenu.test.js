// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { expect, test, vi } from 'vitest'
import CellContextMenu from '../src/components/smart/grid/CellContextMenu.vue'

test('one whole row shows record actions while multi-row and cell-block selections show delete count', async () => {
  const menu = mount(CellContextMenu, {
    props: { x: 10, y: 10, rowOnly: true, rangeRowCount: 1, canCreate: true, canDelete: true },
    global: { stubs: { Teleport: true } },
  })
  expect(menu.findAll('button').map(b => b.text())).toEqual(['展开记录', '创建副本', '向上插入', '向下插入', '删除'])
  await menu.findAll('button').find(button => button.text() === '向上插入').trigger('click')
  expect(menu.emitted('action')[0]).toEqual(['insert-up', 1])
  await menu.setProps({ rowOnly: false, rangeRowCount: 5 })
  expect(menu.findAll('button').map(b => b.text())).toEqual(['删除 5 行'])
  await menu.setProps({ rangeRowCount: 1 })
  expect(menu.findAll('button').map(b => b.text())).toEqual(['删除 1 行'])
  menu.unmount()
})

test('hover and keyboard submenu keep DOM containment and follow scroll/resize', async () => {
  vi.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(1024)
  vi.spyOn(document.documentElement, 'clientHeight', 'get').mockReturnValue(768)
  const menu = mount(CellContextMenu, {
    attachTo: document.body,
    props: { x: 200, y: 150, hasField: true, canCreate: true },
    global: { stubs: { Teleport: true } },
  })
  const entry = menu.findAll('.cell-menu-entry').find(entry => entry.text().includes('数据可视化'))
  await entry.trigger('mouseenter')
  await nextTick()
  const sub = menu.find('.cell-menu-sub')
  vi.spyOn(sub.element.parentElement, 'getBoundingClientRect').mockReturnValue({ left: 20, top: 70, right: 220 })
  vi.spyOn(sub.element, 'getBoundingClientRect').mockReturnValue({ width: 192, height: 100 })
  await menu.find('.cell-context-menu').trigger('scroll')
  expect(sub.element.style.position).toBe('fixed')
  expect(sub.element.style.left).toBe('218px')
  expect(sub.element.style.top).toBe('66px')
  await sub.trigger('pointerdown')
  expect(menu.emitted('close')).toBeUndefined()
  window.dispatchEvent(new Event('resize'))
  await nextTick(); await nextTick(); await nextTick()
  expect(menu.emitted('close')).toBeUndefined()
  expect(Number(menu.find('.cell-context-menu').element.style.zIndex)).toBeGreaterThan(4000)
  await menu.findAll('button').find(button => button.text() === '数据可视化').trigger('click')
  expect(menu.find('.cell-menu-sub').exists()).toBe(false)
  await menu.findAll('button').find(button => button.text() === '数据可视化').trigger('keydown', { key: 'ArrowRight' })
  expect(menu.find('.cell-menu-sub').exists()).toBe(true)
  await menu.find('.cell-menu-sub button').trigger('click')
  expect(menu.emitted('action')[0]).toEqual(['viz-bar', undefined])
  menu.unmount()
  vi.restoreAllMocks()
})

test('insert quantity and Escape remain usable in scrolling menu', async () => {
  const menu = mount(CellContextMenu, {
    props: { x: 10, y: 10, canCreate: true },
    global: { stubs: { Teleport: true } },
  })
  const input = menu.find('input')
  await input.setValue(7)
  await input.trigger('keydown', { key: 'Enter' })
  expect(menu.emitted('action')[0]).toEqual(['insert-up', 7])
  await menu.find('.cell-context-menu').trigger('keydown', { key: 'Escape' })
  expect(menu.emitted('close')).toHaveLength(2)
  menu.unmount()
})
