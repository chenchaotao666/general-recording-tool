// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { visibleRowRect } from '../src/smart/utils/vxeCell.js'

test('row controls use a visible anchor after horizontal scrolling', () => {
  const body = document.createElement('div')
  body.className = 'vxe-table--body-wrapper'
  body.innerHTML = '<table><tbody><tr><td></td><td></td><td></td></tr></tbody></table>'
  document.body.append(body)
  const cells = [...body.querySelectorAll('td')]
  const rect = (left, top = 60) => ({ left, right: left + 100, top, bottom: top + 36, width: 100, height: 36 })
  body.getBoundingClientRect = () => ({ left: 0, right: 500, top: 50, bottom: 400 })
  cells[0].getBoundingClientRect = () => rect(-200)
  cells[1].classList.add('fixed--hidden')
  cells[1].getBoundingClientRect = () => rect(0)
  cells[2].getBoundingClientRect = () => rect(100)
  vi.stubGlobal('document', document)
  const original = document.elementFromPoint
  document.elementFromPoint = () => null
  try {
    expect(visibleRowRect(cells)).toEqual(rect(100))
    cells[2].getBoundingClientRect = () => rect(100, 20)
    expect(visibleRowRect(cells)).toBeNull()
  } finally {
    document.elementFromPoint = original
    body.remove()
    vi.unstubAllGlobals()
  }
})
