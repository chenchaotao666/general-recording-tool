import { expect, test } from 'vitest'
import { sampleBrushCurve } from '../src/views/whiteboard/brushCurve'
import { buildPartsSkeleton } from '../src/views/whiteboard/excalidrawAi'

test('closed brush contours preserve endpoints, fill and layer order', () => {
  const points = [[0, 0], [50, -10], [80, 30], [20, 80]]
  const sampled = sampleBrushCurve(points, true)
  expect(sampled).toHaveLength(33)
  expect(sampled[0]).toEqual(sampled.at(-1))
  expect(sampled.flat().every(Number.isFinite)).toBe(true)
  const output = buildPartsSkeleton([{ type: 'drawing', elements: [
    { type: 'curve', x: 20, y: 30, points, closed: true, backgroundColor: '#eecbaa' },
    { type: 'curve', x: 20, y: 30, points, closed: false, backgroundColor: '#ffffff' },
  ] }])
  expect(output[0]).toMatchObject({ type: 'line', backgroundColor: '#eecbaa', roughness: 0 })
  expect(output[1]).toMatchObject({ type: 'line', backgroundColor: 'transparent' })
  expect(output[1].points.at(-1)).toEqual([20, 80])
})
