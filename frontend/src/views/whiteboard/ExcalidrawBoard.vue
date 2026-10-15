<template>
  <div class="react-host">
    <div ref="hostEl" class="react-root"></div>
    <!-- 加载遮罩：工具栏（含注入的平铺按钮）就绪后再撤掉，避免按钮"后出来"的闪动 -->
    <div v-if="!ready" v-loading="true" element-loading-text="画板加载中…" class="boot-overlay" />
  </div>
</template>

<script setup>
// Excalidraw 画布编辑器：React 组件桥接（createRoot 挂载），供画板页使用
// props.initial = serializeAsJSON 产出的 JSON 字符串；change 事件回传同格式字符串
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { createRoot } from 'react-dom/client'
import React from 'react'
import { convertToExcalidrawElements, serializeAsJSON } from '@excalidraw/excalidraw'
import ExcalidrawBoard from './react/ExcalidrawReact'
import { layoutDiagram } from './aiLayout'

const props = defineProps({
  initial: { type: String, default: '' },   // 上次保存的画布 JSON（空 = 新画布）
})
const emit = defineEmits(['change'])

const hostEl = ref(null)
const ready = ref(false)   // 工具栏注入完成（含 200ms 渲染落地缓冲）后才撤遮罩
let root = null
let api = null
// 最新画布状态（onChange 高频回调，用普通变量存，不走响应式）
let elements = []
let appState = null
let files = null
let emitTimer = null

function currentJson() {
  const d = JSON.parse(serializeAsJSON(elements, appState, files, 'local'))
  // serializeAsJSON('local') 的存储配置把视口字段标记为 export:false（scrollX/scrollY/zoom 会被过滤掉），
  // 手动补回，否则刷新后视口回到原点、内容看起来偏移
  if (appState) {
    d.appState = { ...d.appState, scrollX: appState.scrollX, scrollY: appState.scrollY, zoom: appState.zoom }
  }
  return JSON.stringify(d)
}

// 对外：切页/卸载前取最新内容（不经过防抖）
function getContent() {
  clearTimeout(emitTimer)
  return currentJson()
}

// ---------- AI 生成：nodes/edges 结构 → 分层布局（aiLayout 共享）→ excalidraw 骨架元素 → 官方转换器入库 ----------

// nodes/edges → excalidraw 骨架元素（分层布局算坐标；箭头绑定两端节点，由 excalidraw 自动布线）
// 骨架格式：convertToExcalidrawElements 接受 {type, x, y, width, height, label} 简格式
function buildSkeleton(nodes, edges) {
  const pos = layoutDiagram(nodes, edges)
  const shapes = nodes.map((n) => ({
    type: n.shape === 'ellipse' ? 'ellipse' : n.shape === 'diamond' ? 'diamond' : 'rectangle',
    id: n.id,
    x: pos[n.id].x, y: pos[n.id].y,
    width: pos[n.id].width, height: pos[n.id].height,
    label: { text: n.label },
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
      ...(e.label ? { label: { text: e.label } } : {}),
    }
  })
  return [...shapes, ...arrows]
}

// AI 绘画：elements 已带坐标（不做布局）。线/箭头规范化：首点平移到 [0,0]（excalidraw 线元素惯例），
// 并补齐 width/height（骨架格式必需，取折点包围盒）
function buildDrawingSkeleton(elements) {
  return elements.map((e) => {
    if ((e.type === 'line' || e.type === 'arrow') && e.points?.length > 1) {
      const [dx, dy] = e.points[0]
      const pts = e.points.map(([px, py]) => [px - dx, py - dy])
      const xs = pts.map((p) => p[0]); const ys = pts.map((p) => p[1])
      return {
        ...e, x: e.x + dx, y: e.y + dy, points: pts,
        width: Math.max(...xs) - Math.min(...xs),
        height: Math.max(...ys) - Math.min(...ys),
      }
    }
    return e
  })
}

// 追加模式：骨架 id 全部换新（避免与画布已有元素撞 id，箭头绑定同步重指），
// 并整体平移到现有内容右侧（顶对齐），再与现有元素合并入库
function remapForAppend(skeleton, live) {
  const stamp = Date.now().toString(36)
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
        width: colW[c], height: TABLE_ROW_H, label: { text: String(text ?? '') },
      })
      x += colW[c]
    })
  })
  return cells
}

// 多部分（复合需求）：每部分单独生成骨架——id 加 p{i}- 前缀防跨部分撞号（箭头绑定同步重指），
// 各部分横向排开（左对齐到累计偏移，间距 160）
function buildPartsSkeleton(parts) {
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

// 当前选中集合：appState.selectedElementIds + 连带项（容器的文字标签、选中连线上的标签文字），
// 删除/标记选中时按这个集合走，避免留下孤儿标签
function selectedIds() {
  const flags = appState?.selectedElementIds || {}
  const sel = new Set(Object.keys(flags).filter((k) => flags[k]))
  if (!sel.size) return sel
  for (const e of (elements || []).filter((x) => !x.isDeleted)) {
    if (e.type === 'text' && e.containerId && sel.has(e.containerId)) sel.add(e.id)
  }
  return sel
}

// 选中元素的包围盒（局部替换时新内容的落点）
function selectionBBox(live, sel) {
  const picked = live.filter((e) => sel.has(e.id))
  if (!picked.length) return null
  return {
    minX: Math.min(...picked.map((e) => e.x)),
    minY: Math.min(...picked.map((e) => e.y)),
    maxX: Math.max(...picked.map((e) => e.x + (e.width || 0))),
    maxY: Math.max(...picked.map((e) => e.y + (e.height || 0))),
  }
}

// 对外：把 AI 生成的内容应用到画布。单部分与 parts 数组统一走 buildPartsSkeleton；
// drawing=带坐标元素直接转换，diagram=nodes/edges 走分层布局；
// append 时合并而非替换；modify 且有选中元素时只替换选中部分（未选中内容原样保留）。
// 返回是否真正写入（编辑器未就绪/无内容时 false，调用方据此提示）
function applyAiContent(d, { append = false } = {}) {
  if (!api) return false
  const parts = d?.parts?.length ? d.parts : [d]
  const skeleton = buildPartsSkeleton(parts)
  if (!skeleton.length) return false
  const live = (elements || []).filter((el) => !el.isDeleted)

  // 局部替换：modify + 有选中 → 删掉选中元素，新内容放到原选区左上角，视野聚焦新内容
  if (!append && d?.mode === 'modify' && live.length) {
    const sel = selectedIds()
    const bb = sel.size ? selectionBBox(live, sel) : null
    if (bb) {
      const converted = convertToExcalidrawElements(remapForAppend(skeleton, []))
      const skelMinX = Math.min(...converted.map((e) => e.x))
      const skelMinY = Math.min(...converted.map((e) => e.y))
      const dx = bb.minX - skelMinX; const dy = bb.minY - skelMinY
      const placed = converted.map((e) => ({ ...e, x: e.x + dx, y: e.y + dy }))
      api.updateScene({ elements: [...live.filter((e) => !sel.has(e.id)), ...placed] })
      api.scrollToContent(placed, { fitToContent: true, viewportZoomFactor: 0.75 })
      return true
    }
  }

  if (!append) {
    api.updateScene({ elements: convertToExcalidrawElements(skeleton) })
  } else {
    const converted = convertToExcalidrawElements(remapForAppend(skeleton, live))
    api.updateScene({ elements: [...live, ...converted] })
  }
  // viewportZoomFactor 0.75：适配时留边，避免顶部节点被悬浮工具栏遮住
  api.scrollToContent(undefined, { fitToContent: true, viewportZoomFactor: 0.75 })
  return true
}

// 对外：提取画布概要（供 AI 追加/修改/汇总参考）。容器标签文字随宿主上报不重复；
// 箭头带 from/to（绑定端的标签）让模型看懂结构；selected 标记用户当前选中的元素；
// 条数/文字长度截断防 token 爆炸
function getContext() {
  const els = (elements || []).filter((e) => !e.isDeleted).slice(0, 200)
  const sel = selectedIds()
  const labelOf = (e) => {
    if (!e) return ''
    const t = els.find((x) => x.type === 'text' && x.containerId === e.id)
    return (t?.text || '').trim().slice(0, 40)
  }
  const byId = new Map(els.map((e) => [e.id, e]))
  const out = []
  for (const e of els) {
    if (e.type === 'text' && e.containerId) continue
    if (e.type === 'arrow' || e.type === 'line') {
      const item = { type: e.type }
      const text = labelOf(e)
      const from = labelOf(byId.get(e.startBinding?.elementId))
      const to = labelOf(byId.get(e.endBinding?.elementId))
      if (text) item.text = text
      if (from) item.from = from
      if (to) item.to = to
      if (sel.has(e.id)) item.selected = true
      out.push(item)
    } else if (e.type === 'text') {
      if (e.text?.trim()) {
        const item = { type: 'text', text: e.text.trim().slice(0, 60) }
        if (sel.has(e.id)) item.selected = true
        out.push(item)
      }
    } else {
      const item = { type: e.type, x: Math.round(e.x), y: Math.round(e.y) }
      const text = labelOf(e)
      if (text) item.text = text
      if (sel.has(e.id)) item.selected = true
      out.push(item)
    }
  }
  return out
}

function scheduleEmit() {
  clearTimeout(emitTimer)
  emitTimer = setTimeout(() => emit('change', currentJson()), 500)
}

// 默认素材库：后端托管在 /api/excalidrawlibs（不进前端 dist），
// 用户第一次打开素材库面板时才拉取（merge 合并进浏览器本地素材库缓存）
let libsLoaded = false
async function loadDefaultLibraries() {
  if (!api || libsLoaded) return
  libsLoaded = true
  try {
    const res = await fetch('/api/excalidrawlibs/manifest.json')
    if (!res.ok) return
    const files = await res.json()
    const libs = await Promise.all(
      files.map((f) => fetch(`/api/excalidrawlibs/${encodeURIComponent(f)}`)
        .then((r) => (r.ok ? r.json() : null)).catch(() => null))
    )
    const items = libs.filter(Boolean).flatMap((d) => d.libraryItems || [])
    if (items.length) {
      await api.updateLibrary({ libraryItems: items, merge: true, prompt: false, defaultStatus: 'published' })
    }
  } catch (e) {
    console.warn('[whiteboard] 默认素材库加载失败:', e)
    libsLoaded = false   // 失败允许下次打开面板重试
  }
}

onMounted(() => {
  let initialData
  if (props.initial) {
    try {
      const d = JSON.parse(props.initial)
      initialData = {
        elements: d.elements || [],
        appState: d.appState ? { ...d.appState, collaborators: [] } : undefined,
        files: d.files || undefined,
      }
    } catch { /* 损坏数据按空画布处理 */ }
  }
  root = createRoot(hostEl.value)
  root.render(React.createElement(ExcalidrawBoard, {
    initialData,
    onChange: (el, as, f) => {
      elements = el
      appState = as
      files = f
      scheduleEmit()
      // 打开素材库面板（侧边栏展开）时按需加载默认素材库
      if (as?.openSidebar) loadDefaultLibraries()
    },
    onApi: (a) => { api = a; window.__wb = a },   // __wb：调试句柄（e2e 读 scrollX/scrollY 等），与导图 window.__mm 同款
    onReady: () => { ready.value = true },
  }))
})

onBeforeUnmount(() => {
  clearTimeout(emitTimer)
  // 异步卸载，避免 React 18+ 同步 unmount 告警
  Promise.resolve().then(() => root?.unmount())
})

defineExpose({ getContent, applyAiContent, getContext })
</script>

<style scoped>
.react-host { height: 100%; position: relative; }
.react-root { height: 100%; }
.boot-overlay {
  position: absolute; inset: 0; background: #fff; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; z-index: 10;
}
</style>
