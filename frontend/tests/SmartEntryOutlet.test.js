// @vitest-environment jsdom
import { defineComponent, onMounted, onUnmounted, ref } from 'vue'
import { createMemoryHistory, createRouter, useRoute } from 'vue-router'
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test } from 'vitest'
import SmartEntryOutlet from '../src/components/smart/SmartEntryOutlet.vue'

test('table and dashboard round trips preserve each entry instance and state', async () => {
  const mounted = []
  const unmounted = []
  const page = name => defineComponent({
    setup() {
      const route = useRoute()
      const id = route.params.id
      const text = ref(`${name}-${id}`)
      onMounted(() => mounted.push(`${name}-${id}`))
      onUnmounted(() => unmounted.push(`${name}-${id}`))
      return { text }
    },
    template: '<input v-model="text" />',
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/smart', component: SmartEntryOutlet, children: [
        { path: 'table/:id', component: page('table') },
        { path: 'dashboard/:id', component: page('dashboard') },
      ],
    }],
  })
  await router.push('/smart/table/1')
  await router.isReady()
  const wrapper = mount(defineComponent({ template: '<router-view />' }), {
    global: { plugins: [router], stubs: { ElEmpty: true } },
  })
  await flushPromises()
  const originalInput = wrapper.find('input').element
  await wrapper.find('input').setValue('retained table state')
  for (const path of ['/smart/dashboard/2', '/smart/table/3', '/smart/table/1',
    '/smart/dashboard/2', '/smart/table/1']) {
    await router.push(path)
    await flushPromises()
  }
  expect(wrapper.find('input').element).toBe(originalInput)
  expect(wrapper.find('input').element.value).toBe('retained table state')
  expect(mounted).toEqual(['table-1', 'dashboard-2', 'table-3'])
  expect(unmounted).toEqual([])
  wrapper.unmount()
  expect(unmounted).toHaveLength(3)
})
