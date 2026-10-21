// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import ElementPlus from 'element-plus'
import ContactPickerDialog from '../src/components/people/ContactPickerDialog.vue'
import { person, selectedIds, togglePerson } from '../src/components/people/people.js'

test('people selection uses user IDs, deduplicates and handles single selection', () => {
  expect(person({ id: 99, user_id: 2, username: 'Friend' }).id).toBe(2)
  expect(selectedIds(['2', 2, 3])).toEqual([2, 3])
  expect(togglePerson([2], 3, false)).toEqual([3])
  expect(togglePerson([2, 3], 2, true)).toEqual([3])
})

test('directory search, removal and cancel preserve original selection; confirm applies draft', async () => {
  const original = [1]
  const wrapper = mount(ContactPickerDialog, { props: { visible: true, modelValue: original,
    people: [{ id: 1, name: 'Alice' }], directory: { friends: [{ user_id: 2, username: 'Bob' }], groups: [], enterprise: { name: 'Example', members: [{ id: 1, name: 'Alice' }] } } },
    global: { plugins: [ElementPlus], stubs: { 'el-dialog': { template: '<div><slot /></div>' } } } })
  await wrapper.find('input').setValue('Bob')
  expect(wrapper.findAll('.contact-person')).toHaveLength(1)
  await wrapper.find('.contact-person').trigger('click')
  expect(wrapper.findAll('.chosen-person')).toHaveLength(2)
  await wrapper.findAll('footer button')[1].trigger('click')
  expect(wrapper.emitted('confirm')).toBeUndefined()
  expect(original).toEqual([1])
  await wrapper.setProps({ visible: false })
  await wrapper.setProps({ visible: true })
  expect(wrapper.findAll('.chosen-person')).toHaveLength(1)
  await wrapper.find('.chosen-person button').trigger('click')
  await wrapper.findAll('footer button')[0].trigger('click')
  expect(wrapper.emitted('confirm')[0][0]).toEqual([])
  wrapper.unmount()
})
