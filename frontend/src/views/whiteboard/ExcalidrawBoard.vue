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
  return serializeAsJSON(elements, appState, files, 'local')
}

// 对外：切页/卸载前取最新内容（不经过防抖）
function getContent() {
  clearTimeout(emitTimer)
  return currentJson()
}

// ---------- AI 生成：nodes/edges 结构 → 分层布局 → excalidraw 骨架元素 → 官方转换器入库 ----------

// 骨架节点尺寸（convertToExcalidrawElements 接受 {type, x, y, width, height, label} 简格式）
const SKELETON_SIZE = {
  rect: { width: 170, height: 70 },
  ellipse: { width: 130, height: 60 },
  diamond: { width: 190, height: 100 },
}

// 轻量分层布局（无依赖）：最长路径分层 + 层内 barycenter 排序（按父节点平均位置排，减少交叉线）。
// AI 生成的 5~15 节点流程图够用；图变大变复杂后可换 dagre 进一步提升
function layoutDiagram(nodes, edges) {
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

// nodes/edges → excalidraw 骨架元素（分层布局算坐标；箭头绑定两端节点，由 excalidraw 自动布线）
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

// 对外：把 AI 生成的图结构应用到当前画布（替换现有内容，由调用方确认）
function applyDiagram({ nodes, edges }) {
  if (!api || !nodes?.length) return
  const elements = convertToExcalidrawElements(buildSkeleton(nodes, edges))
  api.updateScene({ elements })
  // viewportZoomFactor 0.75：适配时留边，避免顶部节点被悬浮工具栏遮住
  api.scrollToContent(undefined, { fitToContent: true, viewportZoomFactor: 0.75 })
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
    onApi: (a) => { api = a },
    onReady: () => { ready.value = true },
  }))
})

onBeforeUnmount(() => {
  clearTimeout(emitTimer)
  // 异步卸载，避免 React 18+ 同步 unmount 告警
  Promise.resolve().then(() => root?.unmount())
})

defineExpose({ getContent, applyDiagram })
</script>

<style scoped>
.react-host { height: 100%; position: relative; }
.react-root { height: 100%; }
.boot-overlay {
  position: absolute; inset: 0; background: #fff; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; z-index: 10;
}
</style>
