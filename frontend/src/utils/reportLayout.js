// 报表栅格布局：常量 + 自动布局 + 布局规范化（前端唯一事实源，与后端 report_engine 常量保持一致）
export const GRID_COLS = 24
export const ROW_HEIGHT = 40 // px
export const GRID_MARGIN = 12 // px
export const PAGES_MAX = 10

// 各区块类型的 最小/默认 尺寸（w×h，栅格单位）
export const BLOCK_SIZE = {
  stat: { min: [4, 3], def: [6, 4] },
  chart: { min: [6, 6], def: [12, 10] },
  pivot: { min: [8, 8], def: [24, 12] },
  table: { min: [8, 6], def: [24, 12] },
  text: { min: [4, 2], def: [12, 4] },
  filter: { min: [4, 2], def: [4, 2] },
}

export const BLOCK_TYPE_LABELS = { stat: '统计卡', chart: '图表', pivot: '透视表', table: '明细表', text: '文本', filter: '筛选' }

/** 拖字段成图：按字段类型给默认区块配置（不含 id，调用方分配）。 */
export function smartBlockForField(f) {
  const filters = { logic: 'AND', rules: [] }
  if (['int', 'decimal'].includes(f.data_type)) {
    return { type: 'stat', title: `${f.label}求和`, agg: 'sum', field: f.field_name, filters }
  }
  if (['date', 'datetime'].includes(f.data_type)) {
    return {
      type: 'chart', title: `按月趋势`, chart_type: 'line',
      group: { kind: 'month', field: f.field_name }, agg: 'count', field: null, top_n: 30,
      metrics: [], group2: { field: null }, stack: false, on_click: 'drill', filters,
    }
  }
  return {
    type: 'chart', title: `按${f.label}统计`, chart_type: 'bar',
    group: { kind: 'field', field: f.field_name }, agg: 'count', field: null, top_n: 12,
    metrics: [], group2: { field: null }, stack: false, on_click: 'drill', filters,
  }
}

let pageSeq = 0
export function nextPageId(pages) {
  const existing = new Set(pages.map((p) => p.id))
  do { pageSeq += 1 } while (existing.has(`p${pageSeq}`))
  return `p${pageSeq}`
}

// 在页内寻找追加位置：放当前内容最底部
function appendPos(items, w, h) {
  const y = items.reduce((m, it) => Math.max(m, it.y + it.h), 0)
  return { x: 0, y, w, h }
}

// 单个区块的默认布局项（追加到 items 末尾）
export function defaultItem(block, items = []) {
  const size = BLOCK_SIZE[block.type] || BLOCK_SIZE.text
  return { block_id: block.id, ...appendPos(items, ...size.def) }
}

/**
 * 自动布局：统计卡每行 4 张流式；图表半宽可两两并排；其余通栏。
 * blocks 为模板区块数组，返回完整 layout 对象（单页"总览"）。
 */
export function autoLayout(blocks, title = '总览') {
  const items = []
  let x = 0, y = 0, rowH = 0
  const newline = () => { x = 0; y += rowH; rowH = 0 }
  for (const b of blocks) {
    const [w, h] = (BLOCK_SIZE[b.type] || BLOCK_SIZE.text).def
    const full = w >= GRID_COLS
    if ((full && x > 0) || (!full && x + w > GRID_COLS)) newline()
    items.push({ block_id: b.id, x, y, w, h })
    if (full) { y += h } else { x += w; rowH = Math.max(rowH, h) }
  }
  return {
    version: 1,
    grid: { cols: GRID_COLS, row_height: ROW_HEIGHT },
    pages: [{ id: 'p1', title, items }],
  }
}

/** 规范化布局：剔除悬空引用、裁剪越界坐标、补齐缺省字段、消解重叠。返回新对象（不改入参）。 */
export function normalizeLayout(layout, blocks) {
  const byId = new Map(blocks.map((b) => [b.id, b]))
  const seen = new Set()
  const pages = (layout?.pages || []).map((p) => {
    const items = (p.items || [])
      .filter((it) => {
        const b = byId.get(it.block_id)
        if (!b || seen.has(it.block_id)) return false
        seen.add(it.block_id)
        return true
      })
      .map((it) => {
        const b = byId.get(it.block_id)
        const { min } = BLOCK_SIZE[b.type] || BLOCK_SIZE.text
        const w = Math.min(Math.max(it.w || min[0], min[0]), GRID_COLS)
        return {
          block_id: it.block_id,
          x: Math.min(Math.max(it.x || 0, 0), GRID_COLS - w),
          y: Math.max(it.y || 0, 0),
          w,
          h: Math.max(it.h || min[1], min[1]),
        }
      })
    // 防重叠兜底：查看端按 y,x 顺序把压叠的块逐格下移（坐标被钳制/旧数据异常时仍不叠图）
    const placed = []
    for (const it of items.sort((a, b) => a.y - b.y || a.x - b.x)) {
      let guard = 0
      while (guard++ < 500 && placed.some((q) => it.x < q.x + q.w && it.x + it.w > q.x && it.y < q.y + q.h && it.y + it.h > q.y)) {
        it.y += 1
      }
      placed.push(it)
    }
    return { id: p.id, title: p.title || '未命名', items }
  })
  return {
    version: 1,
    grid: { cols: GRID_COLS, row_height: layout?.grid?.row_height || ROW_HEIGHT },
    pages: pages.length ? pages : [{ id: 'p1', title: '总览', items: [] }],
  }
}

/** 未出现在任何页签中的区块（"未放置"） */
export function unplacedBlocks(layout, blocks) {
  const placed = new Set((layout?.pages || []).flatMap((p) => (p.items || []).map((it) => it.block_id)))
  return blocks.filter((b) => !placed.has(b.id))
}

/** 页内区块按 y,x 排序后的渲染序列（窄屏降级/导出平铺共用） */
export function orderedPageBlocks(page, blocks) {
  const byId = new Map(blocks.map((b) => [b.id, b]))
  return [...(page?.items || [])]
    .sort((a, b2) => a.y - b2.y || a.x - b2.x)
    .map((it) => byId.get(it.block_id))
    .filter(Boolean)
}
