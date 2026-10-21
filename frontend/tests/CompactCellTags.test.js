// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import CompactCellTags from '../src/components/smart/grid/CompactCellTags.vue'

test('empty and single tags avoid layout observers; multiple tags observe only when needed', async () => {
  const observe = vi.fn(), disconnect = vi.fn()
  const Observer = vi.fn(function () { this.observe = observe; this.unobserve = vi.fn(); this.disconnect = disconnect })
  vi.stubGlobal('ResizeObserver', Observer)
  const wrapper = mount(CompactCellTags, { props: { tags: [] } })
  try {
    await wrapper.setProps({ tags: [{ key: 'a', label: '浙江' }] })
    expect(Observer).not.toHaveBeenCalled()
    expect(wrapper.find('.compact-ghost').exists()).toBe(false)
    expect(wrapper.find('.compact-label').text()).toBe('浙江')
    await wrapper.setProps({ tags: [{ key: 'a', label: '浙江' }, { key: 'b', label: '江苏' }] })
    expect(Observer).toHaveBeenCalledTimes(1)
    expect(observe).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ tags: [{ key: 'b', label: '江苏' }] })
    expect(disconnect).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.compact-tag')).toHaveLength(1)
  } finally { wrapper.unmount(); vi.unstubAllGlobals() }
})
