// vxe-table 冻结列会把同一单元格渲染多份（4.22 起都在 body-inner-wrapper 内，非显示副本带
// fixed--hidden = visibility:hidden；旧版在 fixed-left/right wrapper），且 fixed--hidden 类
// 是渲染后补的。单元格内的编辑器/浮层只能由「用户看得见的那一份」驱动，否则多实例互抢焦点、
// 浮层定位到隐藏副本（错位或看不见）。等一帧后按实际可见性判定。
export function isDisplayCell(td) {
  if (!td || !td.isConnected) return false
  if (td.classList.contains('fixed--hidden')) return false
  if (getComputedStyle(td).visibility === 'hidden') return false
  const r = td.getBoundingClientRect()
  if (!r.width || !r.height) return false
  // 多份都可见时（叠放），取最上层那份
  const x = Math.min(Math.max(r.left + r.width / 2, 0), window.innerWidth - 1)
  const y = Math.min(Math.max(r.top + r.height / 2, 0), window.innerHeight - 1)
  const hit = document.elementFromPoint(x, y)
  const hitTd = hit?.closest?.('td')
  const sameCell = hitTd && hitTd.getAttribute('colid') === td.getAttribute('colid')
    && hitTd.parentElement?.getAttribute('rowid') === td.parentElement?.getAttribute('rowid')
  if (!sameCell) return true   // 被浮层盖住或在视口外：不否决
  return hitTd === td
}

export function afterFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()))
}

// 单元格当前在表格可视区内的位置：上下方向只要有一部分被表头/统计行遮住（或滚出）就返回 null（浮层会盖到表头上），
// 左右方向完全滚出才返回 null。
// 用于 teleport 到 body 的浮层（文本编辑框 / 选项面板）在表格滚动时跟随单元格、滚出时隐藏
export function visibleCellRect(td) {
  if (!td || !td.isConnected) return null
  const r = td.getBoundingClientRect()
  const body = td.closest('.vxe-table--body-wrapper')
  if (!body) return r
  const b = body.getBoundingClientRect()
  if (r.top < b.top - 1 || r.bottom > b.bottom + 1 || r.right <= b.left + 1 || r.left >= b.right - 1) return null
  return r
}
