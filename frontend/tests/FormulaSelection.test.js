// @vitest-environment jsdom
import { expect, test, vi } from 'vitest'
import { bracketPair, updateFormulaSelection } from '../src/smart/utils/formulaSelection.js'

test('brackets match the innermost call and ignore quoted parentheses', () => {
  expect(bracketPair('SUM(YEAR(x))', 9)).toEqual([8, 10])
  expect(bracketPair('CONCAT("(", x)', 12)).toEqual([6, 13])
  expect(bracketPair('YEAR(x)', 4)).toEqual([4, 6])
  expect(bracketPair('YEAR(x)', 7)).toEqual([4, 6])
  expect(bracketPair('YEAR(', 5)).toBeNull()
})

test('selected field highlights its surrounding brackets without editing DOM content', () => {
  const highlights = new Map()
  vi.stubGlobal('CSS', { highlights })
  vi.stubGlobal('Highlight', class { constructor(...ranges) { this.ranges = ranges } })
  const editor = document.createElement('div')
  editor.innerHTML = 'YEAR(<span class="fxe-chip" contenteditable="false"><span>Date</span></span>)'
  document.body.appendChild(editor)
  try {
    const chip = editor.querySelector('.fxe-chip')
    const range = document.createRange()
    range.selectNode(chip)
    const selection = window.getSelection()
    selection.removeAllRanges(); selection.addRange(range)
    updateFormulaSelection(editor)
    expect(chip.classList.contains('is-selected')).toBe(true)
    expect(highlights.get('formula-brackets').ranges.map(r => r.toString())).toEqual(['(', ')'])
    expect(editor.textContent).toBe('YEAR(Date)')
    range.setStart(editor.firstChild, 0); range.collapse(true)
    selection.removeAllRanges(); selection.addRange(range)
    updateFormulaSelection(editor)
    expect(chip.classList.contains('is-selected')).toBe(false)
    expect(highlights.has('formula-brackets')).toBe(false)
  } finally { editor.remove(); window.getSelection().removeAllRanges(); vi.unstubAllGlobals() }
})
