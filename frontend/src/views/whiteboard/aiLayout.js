// AI 内容布局（ExcalidrawBoard/DrawioBoard 共用）：
// 结构图骨架尺寸 + 轻量分层布局（无依赖：最长路径分层 + 层内 barycenter 排序，减少交叉线）
export const SKELETON_SIZE = {
  rect: { width: 170, height: 70 },
  ellipse: { width: 130, height: 60 },
  diamond: { width: 190, height: 100 },
}

// AI 生成的 5~15 节点流程图够用；图变大变复杂后可换 dagre 进一步提升
export function layoutDiagram(nodes, edges) {
  const H_SEP = 90; const V_SEP = 100; const LAYER_H = 100
  const ids = new Set(nodes.map((n) => n.id))
  const succs = new Map(nodes.map((n) => [n.id, []]))
  const preds = new Map(nodes.map((n) => [n.id, []]))
  edges.forEach((e) => {
    if (ids.has(e.source) && ids.has(e.target)) {
      succs.get(e.source).push(e.target)
      preds.get(e.target).push(e.source)
    }
  })
  // 最长路径分层（带路径防环：AI 输出的回边会造成环）
  const rank = new Map()
  const visit = (id, r, guard) => {
    if (guard.has(id)) return   // 环：不再下钻
    if ((rank.get(id) ?? -1) >= r) return
    rank.set(id, r)
    const next = new Set(guard); next.add(id)
    succs.get(id).forEach((t) => visit(t, r + 1, next))
  }
  nodes.forEach((n) => visit(n.id, 0, new Set()))
  nodes.forEach((n) => { if (!rank.has(n.id)) rank.set(n.id, 0) })

  const layerList = []
  nodes.forEach((n) => {
    const r = rank.get(n.id)
    while (layerList.length <= r) layerList.push([])
    layerList[r].push(n)
  })

  // 层内排序：两轮 barycenter（按父节点在上一层的平均位置），减少层间交叉
  const idxOf = new Map()
  const reindex = () => {
    idxOf.clear()
    layerList.forEach((l, li) => l.forEach((n, i) => idxOf.set(n.id, { li, i })))
  }
  reindex()
  for (let pass = 0; pass < 2; pass++) {
    for (let li = 1; li < layerList.length; li++) {
      const layer = layerList[li]
      const cur = new Map(layer.map((n, i) => [n.id, i]))
      const bary = (n) => {
        const ps = preds.get(n.id).map((p) => idxOf.get(p)).filter(Boolean)
        return ps.length ? ps.reduce((s, p) => s + p.i, 0) / ps.length : cur.get(n.id)
      }
      layer.sort((a, b) => bary(a) - bary(b))
      reindex()
    }
  }

  // 赋坐标：层内水平排开并围绕 x=0 居中，层距按固定层高累计
  const pos = {}
  layerList.forEach((layer, li) => {
    const widths = layer.map((n) => SKELETON_SIZE[n.shape || 'rect'].width)
    const total = widths.reduce((a, b) => a + b, 0) + H_SEP * (layer.length - 1)
    let x = -total / 2
    layer.forEach((n, i) => {
      pos[n.id] = { x, y: li * (LAYER_H + V_SEP), ...SKELETON_SIZE[n.shape || 'rect'] }
      x += widths[i] + H_SEP
    })
  })
  return pos
}
