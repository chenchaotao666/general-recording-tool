// 树形目录拖拽排序通用逻辑（记事本/画板/思维导图共用，配套样式 tree-dnd.css + 把手组件 DndHandle.vue）
//
// 用法：
//   const dnd = useTreeDnd({ items: notes, visible: displayTree, persist: updateNote, reload: loadTree, onMoved })
//   行元素：:draggable + @dragstart/@dragover/@drop/@dragend 绑定 dnd.start/over/drop/end，
//           :class 里加 dnd.indicatorClass(n)；<DndHandle /> 放在行首作视觉把手（六点 grip）。
//
// 交互约定：拖到条目上半/下半 = 排到其前/后（跟随目标层级）；拖到文件夹中部 = 移入该文件夹。
// 落点指示统一为"上沿一条蓝线"（= 插到这行上面）：拖到下半区时线画在下一可见行的上沿，
// 只有整个列表末尾才用下沿线——上/下两条线表达的是同一个位置，不重复显示。
// 排序模型：扁平列表 + parent_id + sort（0,10,20…），落点后整层重排 sort 并清掉 pinned。
import { ref } from 'vue'

export function useTreeDnd({ items, visible, persist, reload, onMoved }) {
  const dragOver = ref({ id: null, zone: null, lineId: null, lineZone: null })
  let dragId = null
  let blocked = new Set()   // 被拖项的子孙 id：防止把文件夹拖进自己的子树造成环

  // n 的子孙 id 集合（拖起时算一次；若逐 dragover 事件计算会卡顿）
  function descendantIds(id) {
    const out = new Set()
    let grew = true
    while (grew) {
      grew = false
      for (const x of items.value) {
        if (x.parent_id && (x.parent_id === id || out.has(x.parent_id)) && !out.has(x.id)) {
          out.add(x.id)
          grew = true
        }
      }
    }
    return out
  }

  function start(n, e) {
    dragId = n.id
    blocked = descendantIds(n.id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(n.id))   // Firefox 必须 setData 才会触发拖拽
    e.stopPropagation()
  }

  function over(n, e) {
    if (dragId === null || n.id === dragId || blocked.has(n.id)) return
    const r = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientY - r.top) / r.height
    let zone = ratio < 0.5 ? 'before' : 'after'
    if (n.kind === 'folder' && ratio >= 0.3 && ratio <= 0.7) zone = 'into'
    e.preventDefault()   // 不 preventDefault 浏览器不允许 drop
    e.dataTransfer.dropEffect = 'move'
    // dragover 触发极频繁：只有落点变化才写响应式状态，避免拖拽过程中整树反复重渲染
    if (dragOver.value.id === n.id && dragOver.value.zone === zone) return
    // 拖到下半区时，线画在下一可见行的上沿（与"插到本行下面"同一位置，只保留一条线）；
    // 没有下一行（列表末尾）才用本行下沿线。被拖行本身跳过。
    let lineId = n.id
    let lineZone = zone
    if (zone === 'after') {
      const list = visible?.value || []
      const i = list.findIndex((x) => x.id === n.id)
      const next = list.slice(i + 1).find((x) => x.id !== dragId)
      if (next) { lineId = next.id; lineZone = 'before' }
    }
    dragOver.value = { id: n.id, zone, lineId, lineZone }
  }

  async function drop(n, e) {
    e.preventDefault()
    const zone = dragOver.value.id === n.id ? dragOver.value.zone : null
    const drag = items.value.find((x) => x.id === dragId)
    end()
    if (!drag || !zone) return
    const newParentId = zone === 'into' ? n.id : (n.parent_id || null)
    // 目标层级的兄弟按当前展示顺序（与后端一致：pinned > sort > updated_at），再插入被拖项
    const sibs = items.value
      .filter((x) => (x.parent_id || null) === newParentId && x.id !== drag.id)
      .sort((a, b) => ((b.pinned - a.pinned) || (a.sort - b.sort)
        || (b.updated_at > a.updated_at ? 1 : b.updated_at < a.updated_at ? -1 : 0)))
    let idx = zone === 'into' ? sibs.length : sibs.findIndex((x) => x.id === n.id)
    if (zone === 'after') idx += 1
    sibs.splice(idx, 0, drag)
    const jobs = []
    sibs.forEach((x, i) => {
      const sort = i * 10
      const p = { sort, pinned: false }
      if (x.id === drag.id) p.parent_id = newParentId
      if (x.sort !== sort || x.pinned || x.id === drag.id) jobs.push(persist(x.id, p))
    })
    await Promise.all(jobs)
    await onMoved?.(zone, n, drag)
    await reload()
  }

  function end() {
    dragId = null
    blocked = new Set()
    dragOver.value = { id: null, zone: null, lineId: null, lineZone: null }
  }

  function indicatorClass(n) {
    const d = dragOver.value
    if (d.id === n.id && d.zone === 'into') return 'dnd-into'
    if (d.zone && d.zone !== 'into' && d.lineId === n.id) return d.lineZone === 'before' ? 'dnd-before' : 'dnd-after'
    return ''
  }

  return { dragOver, start, over, drop, end, indicatorClass }
}
