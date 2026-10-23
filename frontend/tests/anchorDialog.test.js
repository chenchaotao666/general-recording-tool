// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { h, nextTick, ref } from 'vue'
import { anchoredDialogAttrs, useButtonAnchoredDialog } from '../src/smart/utils/anchorDialog.js'

let wrappers
let observers
beforeEach(() => {
  wrappers = []
  observers = []
  vi.stubGlobal('innerWidth', 1000)
  vi.stubGlobal('innerHeight', 800)
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) {
      this.callback = callback
      this.observe = vi.fn()
      this.disconnect = vi.fn()
      observers.push(this)
    }
  })
})
afterEach(() => {
  wrappers.forEach(wrapper => wrapper.unmount())
  vi.unstubAllGlobals()
})

function dialog(at = { x: 900, y: 700 }, rect = {}) {
  const anchor = ref(at)
  const open = ref(true)
  const dimensions = { width: 400, height: 300, ...rect }
  let opened
  const wrapper = mount({
    setup() {
      const body = ref(null)
      opened = useButtonAnchoredDialog(() => body.value, () => anchor.value, () => open.value)
      return () => h('div', { class: 'el-dialog', style: anchoredDialogAttrs(anchor.value, 400, 200).style }, [h('div', { ref: body })])
    },
  })
  wrappers.push(wrapper)
  const panel = wrapper.element
  panel.getBoundingClientRect = () => ({
    left: parseFloat(panel.style.left || panel.style.getPropertyValue('--st-dialog-left')) || 300,
    top: parseFloat(panel.style.top || panel.style.getPropertyValue('--st-dialog-top')) || 120,
    width: Math.min(dimensions.width, window.innerWidth - 24),
    height: Math.min(dimensions.height, parseFloat(panel.style.maxHeight) || dimensions.height),
  })
  for (const [key, prop] of Object.entries({offsetLeft:'left',offsetTop:'top',offsetWidth:'width',offsetHeight:'height'})) {
    Object.defineProperty(panel, key, {get:()=>panel.getBoundingClientRect()[prop]})
  }
  return { wrapper, panel, dimensions, anchor, open, opened }
}

describe('anchoredDialogAttrs', () => {
  test('unanchored dialogs retain default positioning with viewport bounds and scrolling', () => {
    const attrs = anchoredDialogAttrs(null)
    expect(attrs.class).toBeUndefined()
    expect(attrs.style.left).toBeUndefined()
    expect(attrs.style.top).toBeUndefined()
    expect(attrs.style.maxWidth).toBe('calc(100vw - 24px)')
    expect(attrs.style.maxHeight).toContain('100vh')
    expect(attrs.style.maxHeight).toContain('--el-dialog-margin-top')
    expect(attrs.style.overflowY).toBe('auto')
  })

  test('initial mouse and button positions preserve estimate-based semantics', () => {
    for (const placement of [undefined, 'button']) {
      const attrs = anchoredDialogAttrs({ x: 990, y: 790, placement }, 400, 200)
      expect(attrs.style['--st-dialog-left']).toBe('588px')
      expect(attrs.style['--st-dialog-top']).toBe('588px')
      expect(attrs.style.maxWidth).toBe('calc(100vw - 24px)')
      expect(attrs.style.maxHeight).toContain(placement ? '24px' : '600px')
      expect(attrs.style.overflowY).toBe('auto')
    }
    const attrs = anchoredDialogAttrs({ x: -200, y: -100 })
    expect(attrs.style['--st-dialog-left']).toBe('12px')
    expect(attrs.style['--st-dialog-top']).toBe('12px')
  })

  test('FindReplace-style overrides preserve width and scrolling', () => {
    const attrs = anchoredDialogAttrs(null, 400, 380)
    attrs.style = { ...attrs.style, left: '80px', top: '50px', right: 'auto', maxHeight: 'calc(100vh - 62px)' }
    expect(attrs.style.maxWidth).toBe('calc(100vw - 24px)')
    expect(attrs.style.overflowY).toBe('auto')
    expect(attrs.style.maxHeight).toBe('calc(100vh - 62px)')
  })
})

describe('useButtonAnchoredDialog', () => {
  test('form rerenders preserve the measured position instead of restoring the opening estimate', async () => {
    const { wrapper, panel, opened } = dialog()
    await opened()
    expect(panel.style.top).toBe('488px')
    wrapper.vm.$forceUpdate()
    await nextTick()
    expect(panel.style.top).toBe('488px')
    expect(panel.style.left).toBe('588px')
  })

  test('opened corrects mouse-anchor overflow using the measured height', async () => {
    const { panel, opened } = dialog()
    expect(panel.style.getPropertyValue('--st-dialog-top')).toBe('588px')
    await opened()
    expect(panel.style.top).toBe('488px')
    expect(panel.style.left).toBe('588px')
    expect(observers[0].observe).toHaveBeenCalledWith(panel)
    expect(observers[0].observe).toHaveBeenCalledWith(panel.firstChild)
  })

  test('content growth and window resize clamp ordinary anchors without snapping back', async () => {
    const { panel, dimensions, opened } = dialog({ x: 100, y: 100 })
    await opened()
    expect(panel.style.top).toBe('104px')
    dimensions.height = 730
    observers[0].callback()
    expect(panel.style.top).toBe('58px')
    dimensions.height = 300
    observers[0].callback()
    expect(panel.style.top).toBe('58px')
    vi.stubGlobal('innerWidth', 450)
    vi.stubGlobal('innerHeight', 250)
    window.dispatchEvent(new Event('resize'))
    expect(panel.style.left).toBe('38px')
    expect(panel.style.top).toBe('12px')
    expect(panel.style.maxHeight).toBe('226px')
    expect(panel.style.overflowY).toBe('auto')
  })

  test.each([
    [{ x: 100, top: 50, bottom: 80, placement: 'button' }, 300, '86px'],
    [{ x: 980, top: 650, bottom: 680, placement: 'button' }, 300, '344px'],
    [{ x: 100, top: 200, bottom: 230, placement: 'button' }, 700, '88px'],
    [{ x: 100, top: 200, bottom: 230, placement: 'button' }, 1000, '12px'],
  ])('button anchors choose below, above or the viewport boundary: %j', async (at, height, top) => {
    const { panel, opened } = dialog(at, { height })
    await opened()
    expect(panel.style.top).toBe(top)
    expect(panel.style.left).toBe(at.x === 980 ? '588px' : '100px')
  })

  test.each([null, { x: 100, y: 100 }, { x: 100, top: 50, bottom: 80, placement: 'button' }])(
    'dragged panels keep their actual position and only clamp overflow: %j', async at => {
      const { panel, dimensions, opened } = dialog(at)
      panel.dataset.panelDragged = 'true'
      panel.style.left = '500px'
      panel.style.top = '400px'
      await opened()
      expect(panel.style.left).toBe('500px')
      expect(panel.style.top).toBe('400px')
      dimensions.height = 500
      observers[0].callback()
      expect(panel.style.left).toBe('500px')
      expect(panel.style.top).toBe('288px')
      vi.stubGlobal('innerWidth', 600)
      vi.stubGlobal('innerHeight', 400)
      window.dispatchEvent(new Event('resize'))
      expect(panel.style.left).toBe('188px')
      expect(panel.style.top).toBe('12px')
    },
  )

  test('unanchored panels stay centered after opening and resize', async () => {
    const { panel, opened } = dialog(null, { height: 2000 })
    await opened()
    window.dispatchEvent(new Event('resize'))
    expect(panel.style.left).toBe('')
    expect(panel.style.top).toBe('')
    expect(panel.style.maxHeight).toContain('--el-dialog-margin-top')
    expect(panel.style.overflowY).toBe('auto')
  })

  test('overlapping opened calls keep one observer and close disconnects it', async () => {
    const { panel, open, opened } = dialog()
    await Promise.all([opened(), opened()])
    expect(observers).toHaveLength(1)
    open.value = false
    await nextTick()
    await nextTick()
    expect(observers[0].disconnect).toHaveBeenCalledOnce()
    const top = panel.style.top
    vi.stubGlobal('innerHeight', 300)
    window.dispatchEvent(new Event('resize'))
    expect(panel.style.top).toBe(top)
  })

  test('unmount disconnects observations, removes resize listener and cancels pending opened', async () => {
    const { wrapper, panel, opened } = dialog()
    await opened()
    const pending = opened()
    const top = panel.style.top
    wrapper.unmount()
    wrappers = []
    await pending
    expect(observers).toHaveLength(1)
    expect(observers[0].disconnect).toHaveBeenCalled()
    vi.stubGlobal('innerHeight', 300)
    window.dispatchEvent(new Event('resize'))
    expect(panel.style.top).toBe(top)
  })
})
