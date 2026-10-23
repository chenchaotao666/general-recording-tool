// Catmull–Rom interpolation: editable line points, no bitmap or SVG embedding.
export function sampleBrushCurve(points, closed = false) {
  const controls = points.map(p => [...p])
  if (closed && controls.length > 2 && controls[0][0] === controls.at(-1)[0] && controls[0][1] === controls.at(-1)[1]) controls.pop()
  const n = controls.length
  if (n < 2) return controls
  const at = i => controls[closed ? (i + n) % n : Math.max(0, Math.min(n - 1, i))]
  const output = []
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const a = at(i - 1), b = at(i), c = at(i + 1), d = at(i + 2)
    for (let step = 0; step < 8; step++) {
      const t = step / 8
      output.push([0, 1].map(axis => .5 * (2 * b[axis] + (-a[axis] + c[axis]) * t
        + (2 * a[axis] - 5 * b[axis] + 4 * c[axis] - d[axis]) * t * t
        + (-a[axis] + 3 * b[axis] - 3 * c[axis] + d[axis]) * t * t * t)))
    }
  }
  output.push([...(closed ? controls[0] : controls.at(-1))])
  return output
}
