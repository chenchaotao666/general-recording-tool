import { layoutDiagram } from './aiLayout'
import { sampleBrushCurve } from './brushCurve'

const styleKeys = ['strokeColor', 'backgroundColor', 'fillStyle', 'strokeStyle', 'strokeWidth', 'roughness', 'opacity', 'fontSize', 'fontFamily', 'textAlign', 'verticalAlign']
const textStyleOf = value => Object.fromEntries(['fontSize', 'fontFamily', 'textAlign', 'verticalAlign'].filter(k => value[k] != null).map(k => [k, value[k]]))
const styleOf = value => Object.fromEntries(styleKeys.filter(key => value[key] != null).map(key => [key, value[key]]))
const labelOf = (text, value) => ({ text, ...textStyleOf(value), ...(value.textColor ? { strokeColor: value.textColor } : {}) })

// Preview and application share the same scene transformation.
export function prepareAiScene(result, live, selected, convert, restoreText) {
  if (result.mode === 'modify' && result.edits?.length) {
    const scene = applyBoardEdits(live, result.edits, selected)
    return restoreText ? reflowEditedText(scene, live, restoreText) : scene
  }
  if (result.mode === 'append' && (result.attachTo || result.parts?.some(p => p.attachTo))) return expandBoardNode(result, live, convert)
  const skeleton = buildPartsSkeleton(result.parts?.length ? result.parts : [result])
  if (!skeleton.length) throw new Error('没有可预览的内容')
  if (result.mode === 'append') return [...live, ...convert(remapForAppend(skeleton, live))]
  const picked = result.mode === 'modify' ? live.filter(e => selected.has(e.id)) : []
  if (picked.length) {
    const added = convert(remapForAppend(skeleton, []))
    const dx = Math.min(...picked.map(e => e.x)) - Math.min(...added.map(e => e.x))
    const dy = Math.min(...picked.map(e => e.y)) - Math.min(...added.map(e => e.y))
    return [...live.filter(e => !selected.has(e.id)), ...added.map(e => ({ ...e, x: e.x + dx, y: e.y + dy }))]
  }
  return convert(skeleton)
}

export function focusAiPreview(result, scene, live) {
  if (result.mode !== 'append') return scene
  const existing = new Set(live.map(e => e.id))
  const parents = new Set([result.attachTo, ...(result.parts || []).map(p => p.attachTo)].filter(Boolean))
  return scene.filter(e => !existing.has(e.id) || parents.has(e.id) || parents.has(e.containerId))
}

export function boardContext(elements, selected = new Set()) {
  const live = elements.filter(e => !e.isDeleted)
  const labels = new Map(live.filter(e => e.type === 'text' && e.containerId).map(e => [e.containerId, e]))
  return live.filter(e => !e.containerId).sort((a, b) => Number(selected.has(b.id)) - Number(selected.has(a.id))).slice(0, 200).map(e => {
    const label = labels.get(e.id)
    return { id: e.id, type: e.type, x: e.x, y: e.y, width: e.width, height: e.height,
      ...styleOf(e), ...(e.angle ? { angle: e.angle } : {}),
      ...(label?.text || e.text ? { text: (label?.text || e.text).slice(0, 1000) } : {}),
      ...(label ? { textColor: label.strokeColor, ...textStyleOf(label) } : {}),
      ...(e.points ? { points: e.points.slice(0, 50) } : {}),
      ...(e.startBinding ? { fromId: e.startBinding.elementId } : {}),
      ...(e.endBinding ? { toId: e.endBinding.elementId } : {}),
      ...(selected.has(e.id) ? { selected: true } : {}) }
  })
}

export function applyBoardEdits(live, edits, selected = new Set()) {
  const byId = new Map(live.map(e => [e.id, e]))
  if (edits.some(edit => !byId.has(edit.id) || selected.size && !selected.has(edit.id))) throw new Error('画布选区已改变，请重新生成修改')
  const patches = new Map(), deleted = new Set()
  for (const edit of edits) {
    const element = byId.get(edit.id)
    const labels = live.filter(e => e.containerId === edit.id)
    if (edit.delete) { deleted.add(edit.id); labels.forEach(e => deleted.add(e.id)); continue }
    const patch = styleOf(edit)
    if (element.type === 'text' && edit.text != null) { patch.text = edit.text; patch.originalText = edit.text }
    if (element.type === 'text' && edit.textColor) patch.strokeColor = edit.textColor
    patches.set(edit.id, patch)
    for (const label of labels) {
      patches.set(label.id, {
        ...(edit.text != null ? { text: edit.text, originalText: edit.text } : {}),
        ...(edit.textColor ? { strokeColor: edit.textColor } : {}),
        ...textStyleOf(edit),
        ...(edit.opacity != null ? { opacity: edit.opacity } : {}),
      })
    }
  }
  return live.filter(e => !deleted.has(e.id)).map(e => {
    const patch = patches.get(e.id) || {}
    if (e.startBinding && deleted.has(e.startBinding.elementId)) patch.startBinding = null
    if (e.endBinding && deleted.has(e.endBinding.elementId)) patch.endBinding = null
    if (e.boundElements?.some(bound => deleted.has(bound.id))) patch.boundElements = e.boundElements.filter(bound => !deleted.has(bound.id))
    if (!Object.keys(patch).length) return e
    return { ...e, ...patch, version: (e.version || 0) + 1, versionNonce: Math.floor(Math.random() * 2147483647), updated: Date.now() }
  })
}

export function reflowEditedText(scene, live, restoreText) {
  const original = new Map(live.map(e => [e.id, e]))
  const changed = new Set(scene.filter(e => e.type === 'text' &&
    ['text', 'fontSize', 'fontFamily', 'textAlign', 'verticalAlign'].some(k => e[k] !== original.get(e.id)?.[k])).map(e => e.id))
  if (!changed.size) return scene
  // The official restorer measures and wraps text. Clone first: it repairs bindings in place.
  const measured = restoreText(structuredClone(scene).map(e => changed.has(e.id)
    ? { ...e, text: e.originalText || e.text } : e), null, { refreshDimensions: true })
  const measuredById = new Map(measured.map(e => [e.id, e]))
  const byId = new Map(scene.map(e => [e.id, e]))
  return scene.map(e => {
    if (!changed.has(e.id)) return e
    const m = measuredById.get(e.id)
    const text = { ...e, text: m.text, width: m.width, height: m.height }
    const parent = byId.get(e.containerId)
    if (!parent || !['rectangle', 'ellipse', 'diamond'].includes(parent.type)) return text
    const factor = parent.type === 'ellipse' ? Math.SQRT1_2 : parent.type === 'diamond' ? .5 : 1
    const width = Math.round(parent.width * factor) - 10, height = Math.round(parent.height * factor) - 10
    const x = parent.x + parent.width * (1 - factor) / 2 + 5
    const y = parent.y + parent.height * (1 - factor) / 2 + 5
    text.x = x + (text.textAlign === 'left' ? 0 : text.textAlign === 'right' ? width - text.width : (width - text.width) / 2)
    text.y = y + (text.verticalAlign === 'top' ? 0 : text.verticalAlign === 'bottom' ? height - text.height : (height - text.height) / 2)
    return text
  })
}

function buildSkeleton(nodes, edges) {
  const pos = layoutDiagram(nodes, edges)
  const shapes = nodes.map((n) => ({
    type: n.shape === 'ellipse' ? 'ellipse' : n.shape === 'diamond' ? 'diamond' : 'rectangle',
    id: n.id,
    x: pos[n.id].x, y: pos[n.id].y,
    width: pos[n.id].width, height: pos[n.id].height,
    ...styleOf(n), label: labelOf(n.label, n),
  }))
  const byId = new Map(shapes.map((s) => [s.id, s]))
  const arrows = edges.map((e, i) => {
    const s = byId.get(e.source)
    const t = byId.get(e.target)
    // 手算正交折线 points（excalidraw 的 elbowed 对程序化箭头不自动布线，直给折点最稳）：
    // 下行边：源底中 → 中横线 → 目标顶中（Z 形）；回边（目标在源上方）：从右侧绕
    const isBack = t.y + t.height <= s.y
    let x; let y; let pts
    if (isBack) {
      const sx = s.x + s.width; const sy = s.y + s.height / 2     // 源右中
      const tx = t.x + t.width; const ty = t.y + t.height / 2   // 目标右中
      const right = Math.max(s.x + s.width, t.x + t.width) + 60
      x = sx; y = sy
      pts = [[0, 0], [right - sx, 0], [right - sx, ty - sy], [tx - sx, ty - sy]]
    } else {
      const sx = s.x + s.width / 2; const sy = s.y + s.height   // 源底中
      const tx = t.x + t.width / 2; const ty = t.y              // 目标顶中
      x = sx; y = sy
      if (Math.abs(tx - sx) < 4) {
        pts = [[0, 0], [tx - sx, ty - sy]]                      // 基本垂直：直线即可
      } else {
        const midY = sy + (ty - sy) / 2
        pts = [[0, 0], [0, midY - sy], [tx - sx, midY - sy], [tx - sx, ty - sy]]
      }
    }
    return {
      type: 'arrow', id: `e${i}`,
      x, y, points: pts,
      width: Math.max(...pts.map((p) => p[0])) - Math.min(...pts.map((p) => p[0])),
      height: Math.max(...pts.map((p) => p[1])) - Math.min(...pts.map((p) => p[1])),
      start: { id: s.id }, end: { id: t.id },
      ...styleOf(e), ...(e.label ? { label: labelOf(e.label, e) } : {}),
    }
  })
  return [...shapes, ...arrows]
}

// AI 绘画：elements 已带坐标（不做布局）。线/箭头规范化：首点平移到 [0,0]（excalidraw 线元素惯例），
// 并补齐 width/height（骨架格式必需，取折点包围盒）
function buildDrawingSkeleton(elements) {
  return elements.map((e) => {
    if (e.type === 'curve') {
      e = { ...e, type: 'line', points: sampleBrushCurve(e.points, e.closed),
        roughness: e.roughness ?? 0, roundness: null,
        backgroundColor: e.closed ? e.backgroundColor : 'transparent' }
    }
    if (e.type === 'text') return { ...e, strokeColor: e.textColor || e.strokeColor || '#1e1e1e' }
    if ((e.type === 'line' || e.type === 'arrow') && e.points?.length > 1) {
      const [dx, dy] = e.points[0]
      const pts = e.points.map(([px, py]) => [px - dx, py - dy])
      const xs = pts.map((p) => p[0]); const ys = pts.map((p) => p[1])
      return {
        ...e, x: e.x + dx, y: e.y + dy, points: pts,
        ...(e.label ? { label: labelOf(e.label.text, e) } : {}),
        width: Math.max(...xs) - Math.min(...xs),
        height: Math.max(...ys) - Math.min(...ys),
      }
    }
    return e.label ? { ...e, label: labelOf(e.label.text, e) } : e
  })
}

// 追加模式：骨架 id 全部换新（避免与画布已有元素撞 id，箭头绑定同步重指），
// 并整体平移到现有内容右侧（顶对齐），再与现有元素合并入库
let appendSequence = 0
export function remapForAppend(skeleton, live) {
  const stamp = `${Date.now().toString(36)}-${++appendSequence}`
  const idMap = new Map()
  let out = skeleton.map((e) => {
    if (!e.id) return e
    const nid = `ai-${stamp}-${e.id}`
    idMap.set(e.id, nid)
    return { ...e, id: nid }
  })
  out = out.map((e) => {
    const s = e.start?.id && idMap.get(e.start.id)
    const t = e.end?.id && idMap.get(e.end.id)
    if (!s && !t) return e
    return { ...e, ...(s ? { start: { id: s } } : {}), ...(t ? { end: { id: t } } : {}) }
  })
  if (live.length) {
    const liveMaxX = Math.max(...live.map((el) => el.x + (el.width || 0)))
    const liveMinY = Math.min(...live.map((el) => el.y))
    const skelMinX = Math.min(...out.map((e) => e.x))
    const skelMinY = Math.min(...out.map((e) => e.y))
    const dx = liveMaxX + 120 - skelMinX; const dy = liveMinY - skelMinY
    out = out.map((e) => ({ ...e, x: e.x + dx, y: e.y + dy }))
  }
  return out
}

// Continue an existing node without rebuilding it or its existing branches.
export function expandBoardNode(result, live, convert) {
  if (result.parts?.length) {
    return result.parts.reduce((scene, part) => expandBoardNode(part, scene, convert), live)
  }
  const parent = live.find(e => e.id === result.attachTo && !e.isDeleted)
  if (!parent) throw new Error('展开目标已不存在，请重新生成')
  const skeleton = remapForAppend(buildPartsSkeleton([result]), [])
  const incoming = new Set(skeleton.filter(e => e.type === 'arrow').map(e => e.end?.id))
  const roots = skeleton.filter(e => e.type !== 'arrow' && !incoming.has(e.id))
  if (!roots.length) throw new Error('新增分支缺少根节点，请重新生成')
  let added = convert(skeleton, { regenerateIds: false })
  const minX = Math.min(...added.map(e => e.x)), minY = Math.min(...added.map(e => e.y))
  const maxX = Math.max(...added.map(e => e.x + e.width))
  const height = Math.max(...added.map(e => e.y + e.height)) - minY
  const x = parent.x + parent.width / 2 - (maxX - minX) / 2
  let y = parent.y + parent.height + 100
  // Move only the new branch down until its bounding box clears existing content.
  const obstacles = live.filter(e => !e.isDeleted && !e.containerId && e.type !== 'arrow' && e.type !== 'line')
  for (let i = 0; i <= obstacles.length; i++) {
    const hits = obstacles.filter(e => e.x < x + maxX - minX + 24 && e.x + e.width > x - 24
      && e.y < y + height + 24 && e.y + e.height > y - 24)
    if (!hits.length) break
    y = Math.max(...hits.map(e => e.y + e.height)) + 100
  }
  added = added.map(e => ({ ...e, x: e.x + x - minX, y: e.y + y - minY }))
  const bindings = new Map()
  const arrows = roots.map((root) => {
    const child = added.find(e => e.id === root.id)
    const sx = parent.x + parent.width / 2, sy = parent.y + parent.height
    const tx = child.x + child.width / 2, ty = child.y
    const [arrow] = convert([{ type: 'arrow', x: sx, y: sy,
      points: [[0, 0], [0, (ty - sy) / 2], [tx - sx, (ty - sy) / 2], [tx - sx, ty - sy]],
      strokeColor: parent.strokeColor, endArrowhead: 'arrow' }])
    arrow.startBinding = { elementId: parent.id, focus: 0, gap: 1 }
    arrow.endBinding = { elementId: child.id, focus: 0, gap: 1 }
    for (const id of [parent.id, child.id]) bindings.set(id, [...(bindings.get(id) || []), { id: arrow.id, type: 'arrow' }])
    return arrow
  })
  return [...live, ...added].map(e => bindings.has(e.id)
    ? { ...e, boundElements: [...(e.boundElements || []), ...bindings.get(e.id)],
      version: (e.version || 0) + 1, versionNonce: Math.floor(Math.random() * 2147483647), updated: Date.now() }
    : e).concat(arrows)
}

// 表格组件 → 矩形网格骨架（excalidraw 无原生表格；列宽按内容估算，20px 字体：中文 ~20px，英文 ~11px）
const TABLE_ROW_H = 50
function buildTableSkeleton(part) {
  const headers = part.headers || []
  const rows = part.rows || []
  if (!headers.length) return []
  const estW = (s) => Array.from(String(s ?? '')).reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? 20 : 11), 0)
  const colW = headers.map((h, c) => {
    let w = estW(h)
    rows.forEach((r) => { w = Math.max(w, estW(r[c])) })
    return Math.min(300, Math.max(100, w + 40))
  })
  const cells = []
  ;[headers, ...rows].forEach((row, r) => {
    let x = 0
    row.forEach((text, c) => {
      cells.push({
        type: 'rectangle', id: `tbl-r${r}c${c}`, x, y: r * TABLE_ROW_H,
        width: colW[c], height: TABLE_ROW_H, ...styleOf(part), label: labelOf(String(text ?? ''), part),
      })
      x += colW[c]
    })
  })
  return cells
}

// 多部分（复合需求）：每部分单独生成骨架——id 加 p{i}- 前缀防跨部分撞号（箭头绑定同步重指），
// 各部分横向排开（左对齐到累计偏移，间距 160）
export function buildPartsSkeleton(parts) {
  const GAP = 160
  const acc = []
  let offsetX = 0
  parts.forEach((part, i) => {
    let skel = part?.type === 'drawing'
      ? buildDrawingSkeleton(part.elements || [])
      : (part?.type === 'component' || (part?.headers && !part?.nodes))
        ? buildTableSkeleton(part)
        : buildSkeleton(part.nodes || [], part.edges || [])
    if (!skel.length) return
    const idMap = new Map()
    skel = skel.map((e) => {
      if (!e.id) return e
      const nid = `p${i}-${e.id}`
      idMap.set(e.id, nid)
      return { ...e, id: nid }
    })
    skel = skel.map((e) => {
      const s = e.start?.id && idMap.get(e.start.id)
      const t = e.end?.id && idMap.get(e.end.id)
      if (!s && !t) return e
      return { ...e, ...(s ? { start: { id: s } } : {}), ...(t ? { end: { id: t } } : {}) }
    })
    const minX = Math.min(...skel.map((e) => e.x))
    skel = skel.map((e) => ({ ...e, x: e.x - minX + offsetX }))
    offsetX = Math.max(...skel.map((e) => e.x + (e.width || 0))) + GAP
    acc.push(...skel)
  })
  return acc
}
