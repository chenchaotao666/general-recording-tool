// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { installVirtualTablePosition } from '../src/smart/utils/virtualTablePosition.js'

test('virtual window offsets stay synchronized and cleanup restores native positioning', async () => {
  const root = document.createElement('div')
  const table = document.createElement('table')
  table.className = 'vxe-table--body'
  table.style.transform = 'translate(539px, 720px)'
  root.append(table)
  const stop = installVirtualTablePosition(root)
  try {
    expect(table.style.getPropertyValue('--st-virtual-x')).toBe('539px')
    expect(table.style.getPropertyValue('--st-virtual-y')).toBe('720px')
    table.style.transform = 'translate(789px, 1080px)'
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(table.style.getPropertyValue('--st-virtual-x')).toBe('789px')
    expect(table.style.getPropertyValue('--st-virtual-y')).toBe('1080px')
    const replacement = table.cloneNode()
    replacement.style.transform = 'translate(0px, 0px)'
    root.replaceChildren(replacement)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(replacement.style.getPropertyValue('--st-virtual-x')).toBe('0px')
    stop()
    expect(replacement.classList.contains('st-virtual-position')).toBe(false)
    expect(replacement.style.transform).toBe('translate(0px, 0px)')
  } finally { stop() }
})

test('cell styles and virtual row replacement do not notify positioning observers', async () => {
  const NativeObserver = globalThis.MutationObserver
  const delivered = vi.fn()
  vi.stubGlobal('MutationObserver', class extends NativeObserver {
    constructor(callback) { super(records => { delivered(records); callback(records) }) }
  })
  const root = document.createElement('div')
  root.innerHTML = '<div><table class="vxe-table--body"><tbody><tr><td>old</td></tr></tbody></table></div>'
  const table = root.querySelector('table')
  table.style.transform = 'translate(0px, 0px)'
  const stop = installVirtualTablePosition(root)
  try {
    table.querySelector('td').style.color = 'red'
    table.querySelector('tbody').innerHTML = '<tr><td>new</td></tr>'
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(delivered).not.toHaveBeenCalled()
    table.style.transform = 'translate(120px, 80px)'
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(table.style.getPropertyValue('--st-virtual-x')).toBe('120px')
  } finally { stop(); vi.unstubAllGlobals() }
})
