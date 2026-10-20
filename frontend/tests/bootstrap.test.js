// @vitest-environment jsdom
import { createApp, defineComponent, h, onMounted } from 'vue'
import { createMemoryHistory, createRouter, RouterView, useRoute } from 'vue-router'
import { flushPromises } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { mountAfterRouteReady } from '../src/bootstrap.js'

test.each([false, true])('initial layout waits for lazy route (redirect: %s)', async redirect => {
  let resolvePage
  const pendingPage = new Promise(resolve => { resolvePage = resolve })
  const layouts = []
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', redirect: '/smart/table/1' },
      { path: '/smart/table/:id', component: () => pendingPage, meta: { flush: true } },
    ],
  })
  const root = defineComponent({
    setup() {
      const route = useRoute()
      onMounted(() => layouts.push({ path: route.path, flush: route.meta.flush }))
      return () => h('main', { class: route.meta.flush ? 'flush' : 'padded' }, h(RouterView))
    },
  })
  const host = document.createElement('div')
  host.textContent = '正在加载…'
  document.body.appendChild(host)
  const navigation = router.push(redirect ? '/' : '/smart/table/1')
  const app = createApp(root).use(router)
  const mounting = mountAfterRouteReady(app, router, host)
  await flushPromises()
  expect(layouts).toEqual([])
  expect(host.textContent).toBe('正在加载…')
  resolvePage(defineComponent({ render: () => h('div', '工作表') }))
  await navigation
  await mounting
  await flushPromises()
  expect(layouts).toEqual([{ path: '/smart/table/1', flush: true }])
  expect(host.querySelector('.padded')).toBeNull()
  expect(host.querySelector('.flush').textContent).toBe('工作表')
  app.unmount()
  host.remove()
})
