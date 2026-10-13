// AI 内容 → drawio mxfile XML 转换（DrawioBoard 专用）：
// 结构图 nodes/edges → 分层布局（aiLayout 共享）→ vertex/edge mxCell（连线交给 drawio 自动布线，不写折点）；
// 绘画 elements → 带坐标的 vertex（形状）/ 自由折线 edge（line/arrow，端点+途经点）
import { layoutDiagram } from './aiLayout'

const SHAPE_STYLE = {
  rect: 'rounded=1;whiteSpace=wrap;html=1;',
  ellipse: 'ellipse;whiteSpace=wrap;html=1;',
  diamond: 'rhombus;whiteSpace=wrap;html=1;',
}
const EDGE_STYLE = 'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;'
const LINE_STYLE = 'rounded=0;html=1;endArrow=none;'

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// ---------- 中间结构：unit ----------
// 顶点 {kind:'v', id, label, shape, x, y, w, h}
// 绑定连线 {kind:'e', id, label, source, target}（结构图，drawio 自动布线）
// 自由折线 {kind:'pl', id, pts:[[x,y],...], arrow}（绘画的 line/arrow，绝对坐标）
// 表格 {kind:'table', id, x, y, w, h, headers, rows, colW}（drawio 原生表格：嵌套 tableRow/单元格）

const TABLE_ROW_H = 40

// 估算文本像素宽（drawio 默认 12px 字体：中文 ~13px，英文/数字 ~7px），用于列宽自适应
function estTextW(s) {
  return Array.from(String(s ?? '')).reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? 13 : 7), 0)
}

function tableUnits(part, prefix) {
  const headers = part.headers || []
  const rows = part.rows || []
  if (!headers.length) return []
  const colW = headers.map((h, c) => {
    let w = estTextW(h)
    rows.forEach((r) => { w = Math.max(w, estTextW(r[c])) })
    return Math.min(240, Math.max(80, w + 24))
  })
  const w = colW.reduce((a, b) => a + b, 0)
  const h = TABLE_ROW_H * (rows.length + 1)
  return [{ kind: 'table', id: `${prefix}tbl`, x: 0, y: 0, w, h, headers, rows, colW }]
}

function diagramUnits(nodes, edges, prefix) {
  const pos = layoutDiagram(nodes, edges)
  const units = nodes.map((n) => ({
    kind: 'v', id: prefix + n.id, label: n.label, shape: n.shape,
    x: pos[n.id].x, y: pos[n.id].y, w: pos[n.id].width, h: pos[n.id].height,
  }))
  edges.forEach((e, i) => units.push({
    kind: 'e', id: `${prefix}e${i}`, label: e.label || '',
    source: prefix + e.source, target: prefix + e.target,
  }))
  return units
}

function drawingUnits(elements, prefix) {
  const units = []
  elements.forEach((e, i) => {
    const id = `${prefix}d${i}`
    if (e.type === 'line' || e.type === 'arrow') {
      if (!e.points?.length) return
      const pts = e.points.map(([px, py]) => [e.x + px, e.y + py])
      units.push({ kind: 'pl', id, pts, arrow: e.type === 'arrow' })
    } else {
      const shape = e.type === 'rectangle' ? 'rect' : e.type
      units.push({ kind: 'v', id, label: '', shape, x: e.x, y: e.y, w: e.width, h: e.height })
    }
  })
  return units
}

// 一个内容部分 → units（id 加前缀防跨部分/跨次撞号）
export function partUnits(part, prefix) {
  if (part?.type === 'component' || (part?.headers && !part?.nodes && !part?.elements)) {
    return tableUnits(part, prefix)
  }
  return part?.type === 'drawing'
    ? drawingUnits(part.elements || [], prefix)
    : diagramUnits(part.nodes || [], part.edges || [], prefix)
}

// units 的包围盒（空数组返回 null）
export function unitsBBox(units) {
  if (!units.length) return null
  const xs = []; const ys = []
  units.forEach((u) => {
    if (u.kind === 'pl') {
      u.pts.forEach(([px, py]) => { xs.push(px); ys.push(py) })
    } else if (u.kind === 'v' || u.kind === 'table') {
      xs.push(u.x, u.x + u.w); ys.push(u.y, u.y + u.h)
    }   // kind 'e' 无坐标，忽略
  })
  if (!xs.length) return null
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) }
}

// 平移 units（连线绑定 id 不受影响）
export function shiftUnits(units, dx, dy) {
  return units.map((u) => {
    if (u.kind === 'v' || u.kind === 'table') return { ...u, x: u.x + dx, y: u.y + dy }
    if (u.kind === 'pl') return { ...u, pts: u.pts.map(([px, py]) => [px + dx, py + dy]) }
    return u
  })
}

// ---------- unit → mxCell XML ----------

function unitXml(u) {
  if (u.kind === 'table') {
    // drawio 原生表格：shape=table 容器 + tableRow 行（相对定位）+ partialRectangle 单元格。
    // 生成后可在 drawio 里继续加行删列、拖动列宽
    const ROW_STYLE = 'shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;'
      + 'top=0;left=0;bottom=0;right=0;collapsible=0;dropTarget=0;fillColor=none;'
      + 'points=[[0,0.5],[1,0.5]];portConstraint=eastwest;html=1;'
    const HEAD_CELL = 'shape=partialRectangle;connectable=0;fillColor=#dae8fc;top=0;left=0;bottom=0;right=0;'
      + 'fontStyle=1;align=center;verticalAlign=middle;overflow=hidden;html=1;'
    const BODY_CELL = 'shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;bottom=0;right=0;'
      + 'align=left;spacingLeft=6;verticalAlign=middle;overflow=hidden;html=1;'
    let xml = `<mxCell id="${esc(u.id)}" value="" style="shape=table;startSize=0;container=1;`
      + `collapsible=0;childLayout=tableLayout;html=1;" vertex="1" parent="1">`
      + `<mxGeometry x="${u.x}" y="${u.y}" width="${u.w}" height="${u.h}" as="geometry"/></mxCell>`
    const allRows = [u.headers, ...u.rows]
    allRows.forEach((row, ri) => {
      const rowId = `${u.id}-r${ri}`
      xml += `<mxCell id="${esc(rowId)}" value="" style="${ROW_STYLE}" vertex="1" parent="${esc(u.id)}">`
        + `<mxGeometry y="${ri * TABLE_ROW_H}" width="${u.w}" height="${TABLE_ROW_H}" as="geometry"/></mxCell>`
      row.forEach((text, ci) => {
        const style = ri === 0 ? HEAD_CELL : BODY_CELL
        xml += `<mxCell id="${esc(rowId)}-c${ci}" value="${esc(text)}" style="${style}" vertex="1"`
          + ` parent="${esc(rowId)}"><mxGeometry width="${u.colW[ci]}" height="${TABLE_ROW_H}" as="geometry">`
          + `<mxRectangle width="${u.colW[ci]}" height="${TABLE_ROW_H}" as="alternateBounds"/>`
          + '</mxGeometry></mxCell>'
      })
    })
    return xml
  }
  if (u.kind === 'v') {
    const style = SHAPE_STYLE[u.shape] || SHAPE_STYLE.rect
    return `<mxCell id="${esc(u.id)}" value="${esc(u.label)}" style="${style}" vertex="1" parent="1">`
      + `<mxGeometry x="${u.x}" y="${u.y}" width="${u.w}" height="${u.h}" as="geometry"/></mxCell>`
  }
  if (u.kind === 'e') {
    const label = u.label ? ` value="${esc(u.label)}"` : ''
    return `<mxCell id="${esc(u.id)}"${label} style="${EDGE_STYLE}" edge="1" parent="1"`
      + ` source="${esc(u.source)}" target="${esc(u.target)}">`
      + '<mxGeometry relative="1" as="geometry"/></mxCell>'
  }
  // 自由折线：首/末点作 sourcePoint/targetPoint，中间点进 Array
  const [sx, sy] = u.pts[0]
  const [tx, ty] = u.pts[u.pts.length - 1]
  const mid = u.pts.slice(1, -1).map(([px, py]) => `<mxPoint x="${px}" y="${py}"/>`).join('')
  const style = u.arrow ? 'rounded=0;html=1;' : LINE_STYLE
  return `<mxCell id="${esc(u.id)}" style="${style}" edge="1" parent="1">`
    + `<mxGeometry relative="1" as="geometry"><mxPoint x="${sx}" y="${sy}" as="sourcePoint"/>`
    + `<mxPoint x="${tx}" y="${ty}" as="targetPoint"/>`
    + (mid ? `<Array as="points">${mid}</Array>` : '')
    + '</mxGeometry></mxCell>'
}

export function unitsToXml(units) {
  return units.map(unitXml).join('')
}

// ---------- mxfile 组装 / 合并 ----------

const MODEL_ATTRS = 'grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1"'
  + ' page="0" pageScale="1" math="0" shadow="0"'

// 替换语义：全新 mxfile。dx/dy 让内容尽量在视口内居中（视口尺寸由调用方量 iframe 容器）
export function buildMxfile(units, viewW, viewH) {
  const bb = unitsBBox(units)
  let dx = 60; let dy = 60
  if (bb) {
    dx = Math.max(40, (viewW - (bb.maxX - bb.minX)) / 2 - bb.minX)
    dy = Math.max(40, (viewH - (bb.maxY - bb.minY)) / 2 - bb.minY)
  }
  return `<mxfile host="embed.diagrams.net"><diagram name="Page-1">`
    + `<mxGraphModel dx="${Math.round(dx)}" dy="${Math.round(dy)}" ${MODEL_ATTRS}><root>`
    + '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    + unitsToXml(units)
    + '</root></mxGraphModel></diagram></mxfile>'
}

// 追加语义：把新 cells 合并进现有 mxfile 的 root（保留原有 dx/dy 视口），解析失败回退 null
export function mergeMxfile(xml, units) {
  if (!xml) return null
  const doc = new DOMParser().parseFromString(xml, 'application/xml')
  if (doc.querySelector('parsererror')) return null
  const model = doc.querySelector('mxGraphModel')
  const root = doc.querySelector('root')
  if (!model || !root) return null
  const frag = new DOMParser().parseFromString(`<root>${unitsToXml(units)}</root>`, 'application/xml')
  if (frag.querySelector('parsererror')) return null
  for (const node of [...frag.documentElement.childNodes]) {
    root.appendChild(doc.importNode(node, true))
  }
  return new XMLSerializer().serializeToString(doc)
}

// 现有画布的顶点包围盒（用于追加时把新内容放到右侧），无内容/解析失败返回 null
export function xmlBBox(xml) {
  if (!xml) return null
  const doc = new DOMParser().parseFromString(xml, 'application/xml')
  if (doc.querySelector('parsererror')) return null
  const xs = []; const ys = []
  for (const cell of doc.querySelectorAll('mxCell[vertex="1"]')) {
    const g = cell.querySelector('mxGeometry')
    if (!g) continue
    const x = parseFloat(g.getAttribute('x') || 0)
    const y = parseFloat(g.getAttribute('y') || 0)
    xs.push(x, x + parseFloat(g.getAttribute('width') || 0))
    ys.push(y, y + parseFloat(g.getAttribute('height') || 0))
  }
  if (!xs.length) return null
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) }
}

// ---------- 画布概要提取（供 AI 追加/修改/汇总参考，格式与 excalidraw 侧一致） ----------

function stripHtml(value) {
  const div = document.createElement('div')
  div.innerHTML = value || ''
  return (div.textContent || '').trim()
}

export function xmlContext(xml) {
  if (!xml) return []
  const doc = new DOMParser().parseFromString(xml, 'application/xml')
  if (doc.querySelector('parsererror')) return []
  const cells = [...doc.querySelectorAll('mxCell')]
  const byId = new Map(cells.map((c) => [c.getAttribute('id'), c]))
  const labelOf = (id) => stripHtml(byId.get(id)?.getAttribute('value') || '').slice(0, 40)
  const out = []
  for (const c of cells) {
    if (c.getAttribute('vertex') === '1') {
      const style = c.getAttribute('style') || ''
      // 表格容器/行没有自身文字，跳过；单元格标 table-cell 让模型看懂是表格内容
      if (style.includes('shape=table;') || style.includes('shape=tableRow')) continue
      const type = style.includes('partialRectangle') ? 'table-cell'
        : style.includes('ellipse') ? 'ellipse'
          : style.includes('rhombus') ? 'diamond' : 'rectangle'
      const item = { type }
      const text = labelOf(c.getAttribute('id'))
      if (text) item.text = text
      out.push(item)
    } else if (c.getAttribute('edge') === '1') {
      const item = { type: (c.getAttribute('style') || '').includes('endArrow=none') ? 'line' : 'arrow' }
      const from = labelOf(c.getAttribute('source'))
      const to = labelOf(c.getAttribute('target'))
      if (from) item.from = from
      if (to) item.to = to
      const text = stripHtml(c.getAttribute('value') || '').slice(0, 40)
      if (text) item.text = text
      out.push(item)
    }
    if (out.length >= 200) break   // 截断防 token 爆炸（与 excalidraw 侧一致）
  }
  return out
}
