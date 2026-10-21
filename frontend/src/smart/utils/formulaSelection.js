// Keep highlighting out of the editable DOM so it cannot disturb the caret or formula.
function content(root, points = []) {
  let text = ''
  function visit(node) {
    if (node.nodeType === 3) {
      for (let i = 0; i < node.nodeValue.length; i++) {
        points.push([node, i])
        text += node.nodeValue[i]
      }
    } else if (node.nodeType === 1 && (node.matches('.fxe-chip') || node.tagName === 'BR')) {
      text += ' '; points.push(null)
    } else for (const child of node.childNodes) visit(child)
  }
  visit(root)
  return text
}

export function bracketPair(text, start, end = start) {
  const stack = [], pairs = []
  let quote = null
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (quote) {
      if (ch === '\\') { i++; continue }
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'") { quote = ch; continue }
    if (ch === '(') stack.push(i)
    if (ch === ')' && stack.length) pairs.push([stack.pop(), i])
  }
  return pairs.find(([a, b]) => start === end && (start === a || start === b + 1))
    || pairs.find(([a, b]) => a < start && end <= b) || null
}

export function updateFormulaSelection(editor) {
  const selection = window.getSelection()
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null
  const inside = range && editor.contains(range.startContainer) && editor.contains(range.endContainer)
  for (const chip of editor.querySelectorAll('.fxe-chip')) {
    chip.classList.toggle('is-selected', !!inside && !range.collapsed && selection.containsNode(chip, false))
  }
  globalThis.CSS?.highlights?.delete('formula-brackets')
  if (!inside || !globalThis.CSS?.highlights || !globalThis.Highlight) return
  const prefix = range.cloneRange()
  prefix.selectNodeContents(editor)
  prefix.setEnd(range.startContainer, range.startOffset)
  const start = content(prefix.cloneContents()).length
  prefix.setEnd(range.endContainer, range.endOffset)
  const end = content(prefix.cloneContents()).length
  const points = []
  const pair = bracketPair(content(editor, points), start, end)
  if (!pair) return
  const ranges = pair.map(index => {
    const [node, offset] = points[index]
    const r = document.createRange()
    r.setStart(node, offset); r.setEnd(node, offset + 1)
    return r
  })
  CSS.highlights.set('formula-brackets', new Highlight(...ranges))
}
