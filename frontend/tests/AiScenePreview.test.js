import { expect, test } from 'vitest'
import { prepareAiScene, focusAiPreview } from '../src/views/whiteboard/excalidrawAi'

const live = [
  { id: 'a', type: 'rectangle', x: 10, y: 20, width: 100, height: 60, strokeColor: '#000000' },
  { id: 'b', type: 'rectangle', x: 200, y: 20, width: 100, height: 60 },
]
const convert = elements => elements.map(e => ({ ...e }))

test('add preview excludes unrelated old content but keeps the branch parent', () => {
  const child = { id: 'new', type: 'rectangle' }
  const scene = [...live, child]
  expect(focusAiPreview({ mode: 'append' }, scene, live)).toEqual([child])
  expect(focusAiPreview({ mode: 'append', attachTo: 'a' }, scene, live)).toEqual([live[0], child])
  expect(focusAiPreview({ mode: 'replace' }, scene, live)).toBe(scene)
})

test('preview edits and deletes without modifying the live scene', () => {
  const result = prepareAiScene({ mode: 'modify', edits: [{ id: 'a', strokeColor: '#ff0000' }, { id: 'b', delete: true }] }, live, new Set(), convert)
  expect(result).toHaveLength(1)
  expect(result[0].strokeColor).toBe('#ff0000')
  expect(live).toHaveLength(2)
  expect(live[0].strokeColor).toBe('#000000')
  expect(prepareAiScene({ mode: 'modify', edits: live.map(e => ({ id: e.id, delete: true })) }, live, new Set(), convert)).toEqual([])
})

test('preview includes existing content for append and preserves unselected content for replacement', () => {
  const drawing = { type: 'drawing', elements: [{ type: 'ellipse', x: 0, y: 0, width: 50, height: 50 }] }
  const appended = prepareAiScene({ ...drawing, mode: 'append' }, live, new Set(), convert)
  expect(appended.slice(0, 2)).toEqual(live)
  expect(appended[2].x).toBeGreaterThan(300)
  const changed = prepareAiScene({ ...drawing, mode: 'modify' }, live, new Set(['a']), convert)
  expect(changed[0]).toBe(live[1])
  expect(changed[1]).toMatchObject({ type: 'ellipse', x: 10, y: 20 })
})
