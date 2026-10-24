// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'
import CompactCellTags from '../src/components/smart/grid/CompactCellTags.vue'
import { createGridLayoutQueue } from '../src/smart/utils/gridLayoutQueue.js'

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

test('virtual remount reuses layout during scrolling; content and width changes invalidate it', async () => {
  let notifyWidth
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) { notifyWidth = callback }
    observe() {} unobserve() {} disconnect() {}
  })
  const frames = new Map()
  let id = 0, width = 100
  vi.stubGlobal('requestAnimationFrame', fn => { frames.set(++id, fn); return id })
  vi.stubGlobal('cancelAnimationFrame', key => frames.delete(key))
  const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
  const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 50 })
  const queue = createGridLayoutQueue()
  const tags = [{ key: 'a', label: 'Alpha' }, { key: 'b', label: 'Beta' }, { key: 'c', label: 'Gamma' }]
  const create = () => mount(CompactCellTags, { props: { tags }, global: { provide: { smartGridLayoutQueue: queue } } })
  const runFrame = async () => {
    const jobs = [...frames.values()]; frames.clear(); jobs.forEach(job => job())
    await flushPromises()
  }
  let wrapper = create()
  try {
    await runFrame()
    expect(bounds).toHaveBeenCalledTimes(3)
    const original = wrapper.text()
    wrapper.unmount()
    queue.pause()
    wrapper = create()
    notifyWidth([{ target: wrapper.element, contentRect: { width } }])
    await flushPromises()
    expect(wrapper.text()).toBe(original)
    expect(bounds).toHaveBeenCalledTimes(3)
    expect(frames.size).toBe(0)
    await wrapper.setProps({ tags: [...tags.slice(0, 2), { key: 'c', label: 'Changed' }] })
    queue.resume()
    await runFrame()
    expect(bounds).toHaveBeenCalledTimes(6)
    width = 180
    notifyWidth([{ target: wrapper.element, contentRect: { width } }])
    await runFrame()
    expect(bounds).toHaveBeenCalledTimes(9)
    expect(wrapper.findAll('.compact-tag')).toHaveLength(3)
  } finally {
    wrapper.unmount(); queue.dispose(); widthSpy.mockRestore(); bounds.mockRestore(); vi.unstubAllGlobals()
  }
})


test('cells resized together measure identical tag content only once per width', async () => {
  let notifyWidth, width = 100, frame
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) { notifyWidth = callback }
    observe() {} unobserve() {} disconnect() {}
  })
  vi.stubGlobal('requestAnimationFrame', callback => { frame = callback; return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => {})
  const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
  const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 50 })
  const queue = createGridLayoutQueue()
  const tags = [{key:'a',label:'Alpha'},{key:'b',label:'Beta'},{key:'c',label:'Gamma'}]
  const cells = Array.from({length:20},()=>mount(CompactCellTags,{props:{tags},global:{provide:{smartGridLayoutQueue:queue}}}))
  try {
    frame(); await flushPromises()
    expect(bounds).toHaveBeenCalledTimes(3)
    width = 180
    notifyWidth(cells.map(cell=>({target:cell.element,contentRect:{width}})))
    frame(); await flushPromises()
    expect(bounds).toHaveBeenCalledTimes(6)
    expect(cells.every(cell=>cell.findAll('.compact-tag').length===3)).toBe(true)
  } finally {
    cells.forEach(cell=>cell.unmount());queue.dispose();widthSpy.mockRestore();bounds.mockRestore();vi.unstubAllGlobals()
  }
})
