import { expect, test } from 'vitest'
import { applyBoardEdits, boardContext, buildPartsSkeleton, expandBoardNode } from '../src/views/whiteboard/excalidrawAi.js'

test('multiple branches reuse model-local IDs without collision and attach to different parents', () => {
  const live = ['a', 'b'].map((id, i) => ({ id, type: 'rectangle', x: i * 500, y: 100, width: 150, height: 60 }))
  let seq = 0
  const convert = items => items.map(item => ({ ...item, id: item.id || `edge-${++seq}`, width: item.width || 0, height: item.height || 0 }))
  const parts = live.map(parent => ({ attachTo: parent.id, nodes: [{ id: 'n1', label: 'New detail' }], edges: [] }))
  const result = expandBoardNode({ parts }, live, convert)
  expect(new Set(result.map(e => e.id)).size).toBe(result.length)
  expect(result.filter(e => e.type === 'arrow').map(e => e.startBinding.elementId)).toEqual(['a', 'b'])
  for (const parent of live) {
    const arrow = result.find(e => e.startBinding?.elementId === parent.id)
    const child = result.find(e => e.id === arrow.endBinding.elementId)
    expect(child.y).toBeGreaterThan(parent.y + parent.height)
  }
})

test('node expansion preserves old branches, places children below and binds both endpoints', () => {
  const parent = { id: 'parent', type: 'rectangle', x: 100, y: 100, width: 160, height: 60, boundElements: [{ id: 'old-edge', type: 'arrow' }] }
  const oldChild = { id: 'old', type: 'rectangle', x: 20, y: 260, width: 400, height: 60 }
  let sequence = 0
  const convert = items => items.map(item => ({ ...item, id: item.id || `generated-${sequence++}`, width: item.width || 0, height: item.height || 0 }))
  const result = expandBoardNode({ attachTo: 'parent', nodes: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], edges: [] }, [parent, oldChild], convert)
  const children = result.filter(e => e.type === 'rectangle' && !['parent', 'old'].includes(e.id))
  expect(children).toHaveLength(2)
  expect(children.every(e => e.y > oldChild.y + oldChild.height)).toBe(true)
  expect(result.find(e => e.id === 'old')).toBe(oldChild)
  expect(parent.boundElements).toHaveLength(1)
  expect(result[0]).toMatchObject({ x: 100, y: 100, width: 160, height: 60 })
  const arrows = result.filter(e => e.type === 'arrow')
  expect(arrows).toHaveLength(2)
  for (const arrow of arrows) {
    expect(arrow.startBinding.elementId).toBe('parent')
    const child = children.find(e => e.id === arrow.endBinding.elementId)
    expect(child.boundElements).toContainEqual({ id: arrow.id, type: 'arrow' })
  }
})

test('diagram shapes, labels and arrows retain independent colors and styles', () => {
  const output = buildPartsSkeleton([{ type: 'diagram', nodes: [
    { id: 'a', label: 'A', backgroundColor: '#ff0000', fillStyle: 'solid', textColor: '#ffffff', roughness: 0 },
    { id: 'b', label: 'B', shape: 'ellipse' },
  ], edges: [{ source: 'a', target: 'b', strokeColor: '#0000ff', strokeStyle: 'dashed', strokeWidth: 3 }] }])
  expect(output[0]).toMatchObject({ backgroundColor: '#ff0000', roughness: 0, label: { text: 'A', strokeColor: '#ffffff' } })
  expect(output[2]).toMatchObject({ strokeColor: '#0000ff', strokeStyle: 'dashed', strokeWidth: 3, start: { id: output[0].id }, end: { id: output[1].id } })
})

test('drawing points normalize without losing style; standalone text and tables keep colors', () => {
  const output = buildPartsSkeleton([{ type: 'drawing', elements: [
    { type: 'line', x: 10, y: 20, points: [[5, 10], [55, 30]], strokeColor: '#123456' },
    { type: 'text', x: 10, y: 20, text: 'Hello', textColor: '#ff0000' },
  ] }, { type: 'component', headers: ['A'], rows: [['B']], backgroundColor: '#ffff00', textColor: '#0000ff' }])
  expect(output[0]).toMatchObject({ points: [[0, 0], [50, 20]], width: 50, height: 20, strokeColor: '#123456' })
  expect(output[1]).toMatchObject({ text: 'Hello', strokeColor: '#ff0000' })
  expect(output[2]).toMatchObject({ backgroundColor: '#ffff00', label: { strokeColor: '#0000ff' } })
})

const scene = [
  { id: 'box', type: 'rectangle', x: 20, y: 30, width: 100, height: 60, strokeColor: '#123456', boundElements: [{ id: 'label', type: 'text' }, { id: 'edge', type: 'arrow' }] },
  { id: 'label', type: 'text', containerId: 'box', text: 'Start', strokeColor: '#000000' },
  { id: 'other', type: 'ellipse', x: 300, y: 30 },
  { id: 'edge', type: 'arrow', points: [[0, 0], [100, 0]], startBinding: { elementId: 'box' }, endBinding: { elementId: 'other' } },
]

test('context carries IDs, geometry, labels, styles and arrow bindings', () => {
  const context = boardContext(scene, new Set(['box']))
  expect(context).toHaveLength(3)
  expect(context[0]).toMatchObject({ id: 'box', width: 100, text: 'Start', textColor: '#000000', selected: true })
  expect(context[2]).toMatchObject({ fromId: 'box', toId: 'other', points: [[0, 0], [100, 0]] })
})

test('color edits preserve positions, IDs, labels and connections', () => {
  const result = applyBoardEdits(scene, [{ id: 'box', backgroundColor: '#ff0000', fillStyle: 'solid', textColor: '#ffffff' }], new Set(['box']))
  expect(result[0]).toMatchObject({ id: 'box', x: 20, y: 30, width: 100, height: 60, backgroundColor: '#ff0000', boundElements: scene[0].boundElements })
  expect(result[1]).toMatchObject({ text: 'Start', strokeColor: '#ffffff' })
  expect(result[2]).toBe(scene[2])
  expect(result[3]).toBe(scene[3])
  expect(scene[0]).not.toHaveProperty('backgroundColor')
  expect(() => applyBoardEdits(scene, [{ id: 'other', delete: true }], new Set(['box']))).toThrow()
})

test('text alignment and font are applied to bound labels and included in context', () => {
  const result = applyBoardEdits(scene, [{ id: 'box', fontSize: 28, fontFamily: 8, textAlign: 'left', verticalAlign: 'top' }], new Set(['box']))
  expect(result[1]).toMatchObject({ fontSize: 28, fontFamily: 8, textAlign: 'left', verticalAlign: 'top', text: 'Start' })
  expect(result[2]).toBe(scene[2])
  expect(result[3]).toBe(scene[3])
  expect(boardContext(result, new Set(['box']))[0]).toMatchObject({ fontSize: 28, fontFamily: 8, textAlign: 'left', verticalAlign: 'top' })
})

test('deletion removes bound text and detaches arrows without removing unrelated shapes', () => {
  const result = applyBoardEdits(scene, [{ id: 'box', delete: true }])
  expect(result.map(e => e.id)).toEqual(['other', 'edge'])
  expect(result[1].startBinding).toBeNull()
  expect(result[1].endBinding).toEqual({ elementId: 'other' })
})
