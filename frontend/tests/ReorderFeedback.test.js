// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { vReorderFeedback } from '../src/smart/utils/reorderFeedback.js'

function setup(indicators = ['', 'drop-after', '']) {
  const list = document.createElement('div')
  const rows = indicators.map(() => document.createElement('div'))
  rows.forEach((row, i) => {
    row.textContent = String(i); list.append(row)
    row.getBoundingClientRect = () => ({ width: 240, height: 32 })
    vReorderFeedback.mounted(row, { value: '' })
  })
  document.body.append(list)
  const transfer = { types: [], setData: vi.fn(), setDragImage: vi.fn() }
  const event = type => { const e = new Event(type, { bubbles: true, cancelable: true }); Object.defineProperty(e, 'dataTransfer', { value: transfer }); return e }
  return { list, rows, transfer, event, cleanup() { rows.forEach(row => vReorderFeedback.beforeUnmount(row)); list.remove() } }
}

test('placeholder uses source dimensions and forwards drop to the logical row', async () => {
  // jsdom has no native DragEvent; exercise the same event contract.
  vi.stubGlobal('DragEvent', class extends Event { constructor(type, options) { super(type, options); this.dataTransfer = options.dataTransfer } })
  const { rows, list, transfer, event, cleanup } = setup()
  const drop = vi.fn()
  rows[1].addEventListener('drop', drop)
  try {
    rows[0].dispatchEvent(event('dragstart'))
    rows[1].dispatchEvent(event('dragover'))
    // Table groups may draw "after" on the next row's upper edge.
    vReorderFeedback.updated(rows[2], { value: { indicator: 'dnd-before', placeholder: true } })
    const placeholder = list.querySelector('.st-reorder-placeholder')
    expect(placeholder.style.height).toBe('32px')
    expect(placeholder.nextSibling).toBe(rows[2])
    expect(transfer.setDragImage).toHaveBeenCalledWith(rows[0], 24, 16)
    placeholder.dispatchEvent(event('drop'))
    expect(drop).toHaveBeenCalledOnce()
    expect(list.querySelector('.st-reorder-placeholder')).toBeNull()
    await Promise.resolve()
  } finally { cleanup(); vi.unstubAllGlobals() }
})

test('cancel and unmount clear both placeholder and group membership feedback', () => {
  const { rows, list, event, cleanup } = setup()
  try {
    rows[0].dispatchEvent(event('dragstart'))
    rows[1].dispatchEvent(event('dragover'))
    vReorderFeedback.updated(rows[1], { value: 'dnd-into' })
    expect(rows[1].classList.contains('st-reorder-into')).toBe(true)
    window.dispatchEvent(new Event('blur'))
    expect(rows[1].classList.contains('st-reorder-into')).toBe(false)
    rows[0].dispatchEvent(event('dragstart'))
    vReorderFeedback.updated(rows[1], { value: 'drop-after' })
    expect(rows[1].classList.contains('st-reorder-after')).toBe(true)
    expect(list.children.length).toBe(3)
    vReorderFeedback.beforeUnmount(rows[0])
    expect(rows[1].classList.contains('st-reorder-after')).toBe(false)
    expect(list.querySelector('.st-reorder-placeholder')).toBeNull()
  } finally { cleanup() }
})

test('compact feedback keeps drop targets and list geometry intact', async () => {
  const { rows, list, event, cleanup } = setup()
  const drop = vi.fn()
  rows[1].addEventListener('drop', drop)
  try {
    rows[0].dispatchEvent(event('dragstart'))
    rows[1].dispatchEvent(event('dragover'))
    vReorderFeedback.updated(rows[2], { value: 'dnd-before' })
    expect(rows[2].classList.contains('st-reorder-before')).toBe(true)
    expect([...list.children]).toEqual(rows)
    expect(list.querySelector('.st-reorder-placeholder')).toBeNull()
    rows[1].dispatchEvent(event('drop'))
    await Promise.resolve()
    expect(drop).toHaveBeenCalledOnce()
    expect(rows[2].classList.contains('st-reorder-before')).toBe(false)
  } finally { cleanup() }
})

test('horizontal feedback moves between destinations and clears when leaving the list', () => {
  const { rows, event, cleanup } = setup()
  try {
    rows[0].dispatchEvent(event('dragstart'))
    vReorderFeedback.updated(rows[1], { value: { indicator: 'drop-before', horizontal: true } })
    expect(rows[1].classList.contains('st-reorder-horizontal')).toBe(true)
    vReorderFeedback.updated(rows[2], { value: { indicator: 'drop-after', horizontal: true } })
    expect(rows[1].classList.contains('st-reorder-before')).toBe(false)
    expect(rows[1].classList.contains('st-reorder-horizontal')).toBe(false)
    expect(rows[2].classList.contains('st-reorder-after')).toBe(true)
    document.body.dispatchEvent(event('dragover'))
    expect(rows[2].classList.contains('st-reorder-after')).toBe(false)
  } finally { cleanup() }
})
