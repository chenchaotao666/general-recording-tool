// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
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
