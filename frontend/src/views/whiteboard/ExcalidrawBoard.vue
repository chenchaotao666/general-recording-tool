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
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { createRoot } from 'react-dom/client'
import React from 'react'
import { CaptureUpdateAction, convertToExcalidrawElements, serializeAsJSON, exportToBlob, restoreElements } from '@excalidraw/excalidraw'
import ExcalidrawBoard from './react/ExcalidrawReact'
import { buildPartsSkeleton, boardContext, prepareAiScene, focusAiPreview } from './excalidrawAi'

const props = defineProps({
  aiStatusText: { type: String, default: 'AI 生成' },
  initial: { type: String, default: '' },   // 上次保存的画布 JSON（空 = 新画布）
})
const emit = defineEmits(['change', 'ai'])   // ai：画布工具栏最左侧的「AI 生成」按钮点击

const hostEl = ref(null)
const ready = ref(false)   // 工具栏注入完成（含 200ms 渲染落地缓冲）后才撤遮罩
let root = null
watch([() => props.aiStatusText, ready], () => {
  const button = hostEl.value?.querySelector('.wb-ai-tool')
  if (!button) return
  const label = button.querySelector('span')
  if (label) {
    label.textContent = props.aiStatusText
    label.setAttribute('aria-live', 'polite')
  }
  button.title = `${props.aiStatusText}，点击打开 AI 面板`
  button.setAttribute('aria-label', button.title)
}, { flush: 'post' })
let api = null
// 最新画布状态（onChange 高频回调，用普通变量存，不走响应式）
let elements = []
let appState = null
let files = null
let emitTimer = null
let previewDraft = null
let previewScene = null

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
// 当前选中集合：appState.selectedElementIds + 连带项（容器的文字标签、选中连线上的标签文字），
// 删除/标记选中时按这个集合走，避免留下孤儿标签
function selectedIds() {
  const flags = appState?.selectedElementIds || {}
  const sel = new Set(Object.keys(flags).filter((k) => flags[k]))
  if (!sel.size) return sel
  for (const e of (elements || []).filter((x) => !x.isDeleted)) {
    if (sel.has(e.id) && e.type === 'text' && e.containerId) sel.add(e.containerId)
  }
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
function applyAiContent(d) {
  if (!api) return false
  const live = (elements || []).filter(e => !e.isDeleted)
  const scene = previewDraft === d && previewScene ? previewScene : prepareAiScene(d, live, selectedIds(), convertToExcalidrawElements, restoreElements)
  api.updateScene({ elements: scene, captureUpdate: CaptureUpdateAction.IMMEDIATELY })
  previewDraft = null
  previewScene = null
  if (!d.edits?.length && !d.attachTo && !d.parts?.some(p => p.attachTo)) {
    api.scrollToContent(undefined, { fitToContent: true, viewportZoomFactor: 0.75 })
  }
  return true
}

// 对外：提取画布概要（供 AI 追加/修改/汇总参考）。容器标签文字随宿主上报不重复；
// 箭头带 from/to（绑定端的标签）让模型看懂结构；selected 标记用户当前选中的元素；
// 条数/文字长度截断防 token 爆炸
function getContext() {
  return boardContext(elements || [], selectedIds())
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
    onAiClick: () => emit('ai'),
  }))
})

onBeforeUnmount(() => {
  clearTimeout(emitTimer)
  // 异步卸载，避免 React 18+ 同步 unmount 告警
  Promise.resolve().then(() => root?.unmount())
})

async function renderAiDraft(draft, { fullScene = false, focusChanges = false } = {}) {
  const live = (elements || []).filter(e => !e.isDeleted)
  let scene = fullScene
    ? prepareAiScene(draft, (elements || []).filter(e => !e.isDeleted), selectedIds(), convertToExcalidrawElements, restoreElements)
    : convertToExcalidrawElements(buildPartsSkeleton(draft.parts?.length ? draft.parts : [draft]))
  if (fullScene) { previewDraft = draft; previewScene = scene }
  if (fullScene && focusChanges) scene = focusAiPreview(draft, scene, live)
  if (!scene.length) {
    const canvas = document.createElement('canvas')
    canvas.width = 800; canvas.height = 400
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = appState?.viewBackgroundColor || '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png')
  }
  const blob = await exportToBlob({ elements: scene, appState: { exportBackground: true, viewBackgroundColor: appState?.viewBackgroundColor || '#ffffff' },
    files: files || {}, mimeType: 'image/jpeg', maxWidthOrHeight: fullScene ? 2400 : 1000 })
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}
defineExpose({ getContent, applyAiContent, getContext, renderAiDraft })
</script>

<style scoped>
.react-host { height: 100%; position: relative; }
.react-root { height: 100%; }
.boot-overlay {
  position: absolute; inset: 0; background: #fff; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; z-index: 10;
}
</style>
