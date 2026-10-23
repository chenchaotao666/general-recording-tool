// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import menuBounds, { placeSubmenu } from '../src/smart/utils/menuBounds'

afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })
function rect(left, top, width, height) { return { left, top, width, height, right: left + width, bottom: top + height } }
function fixture() {
  document.documentElement.style.cssText = ''
  vi.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(320)
  vi.spyOn(document.documentElement, 'clientHeight', 'get').mockReturnValue(240)
  const menu = document.createElement('div')
  menu.innerHTML = '<div class="has-sub"><div class="fm-sub"></div></div>'
  document.body.append(menu)
  const item = menu.firstElementChild
  const sub = item.firstElementChild
  vi.spyOn(item, 'getBoundingClientRect').mockReturnValue(rect(180, 180, 120, 32))
  vi.spyOn(sub, 'getBoundingClientRect').mockImplementation(() => rect(0, 0, Math.min(192, parseFloat(sub.style.maxWidth) || 192), Math.min(300, parseFloat(sub.style.maxHeight) || 300)))
  vi.spyOn(sub, 'getClientRects').mockReturnValue([{}])
  return { menu, item, sub }
}
test('fixed submenu uses measured anchor, flips left and clamps tall content', () => {
  const { item, sub } = fixture()
  placeSubmenu(sub, item)
  expect(sub.style.position).toBe('fixed')
  expect(sub.style.left).toBe('8px')
  expect(sub.style.top).toBe('8px')
  expect(sub.style.maxHeight).toBe('224px')
  expect(sub.style.overflow).toBe('auto')
})
test('submenu minimum width cannot defeat narrow viewport and recovers on resize', () => {
  const { item, sub } = fixture()
  sub.style.minWidth = '260px'
  vi.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(180)
  placeSubmenu(sub, item)
  expect(sub.style.minWidth).toBe('164px')
  expect(sub.style.maxWidth).toBe('164px')
  vi.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(800)
  placeSubmenu(sub, item)
  expect(sub.style.minWidth).toBe('260px')
  expect(sub.style.left).toBe('298px')
})
test('menu layer shares the Element Plus z-index sequence', () => {
  const { menu } = fixture()
  const layer = document.createElement('div')
  layer.className = 'fm-mask'
  document.body.append(layer)
  layer.append(menu)
  menuBounds.mounted(menu, { value: { x: 10, y: 10 } })
  expect(Number(layer.style.zIndex)).toBeGreaterThan(4000)
  expect(menu.style.zIndex).toBe('')
  menuBounds.unmounted(menu)
})

test('hover, nested menu scroll and resize update anchors; unmount removes listeners', () => {
  const { menu, item, sub } = fixture()
  menuBounds.mounted(menu, { value: { x: 300, y: 220 } })
  item.dispatchEvent(new MouseEvent('mouseenter'))
  expect(sub.style.top).toBe('8px')
  sub.getBoundingClientRect.mockImplementation(() => rect(0, 0, 100, 40))
  item.getBoundingClientRect.mockReturnValue(rect(20, 90, 100, 32))
  menu.dispatchEvent(new Event('scroll'))
  expect(sub.style.left).toBe('118px')
  expect(sub.style.top).toBe('86px')
  item.getBoundingClientRect.mockReturnValue(rect(30, 110, 100, 32))
  sub.dispatchEvent(new Event('scroll'))
  expect(sub.style.top).toBe('106px')
  item.getBoundingClientRect.mockReturnValue(rect(30, 150, 100, 32))
  window.dispatchEvent(new Event('resize'))
  expect(sub.style.top).toBe('146px')
  menuBounds.unmounted(menu)
  item.getBoundingClientRect.mockReturnValue(rect(30, 50, 100, 32))
  window.dispatchEvent(new Event('resize'))
  menu.dispatchEvent(new Event('scroll'))
  expect(sub.style.top).toBe('146px')
})
