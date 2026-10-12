<template>
  <div ref="hostEl" class="react-host"></div>
</template>

<script setup>
// Excalidraw 画布编辑器：React 组件桥接（createRoot 挂载），供画板页使用
// props.initial = serializeAsJSON 产出的 JSON 字符串；change 事件回传同格式字符串
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { createRoot } from 'react-dom/client'
import React from 'react'
import { serializeAsJSON, exportToBlob } from '@excalidraw/excalidraw'
import { ElMessage } from 'element-plus'
import ExcalidrawBoard from './react/ExcalidrawReact'

const props = defineProps({
  initial: { type: String, default: '' },   // 上次保存的画布 JSON（空 = 新画布）
})
const emit = defineEmits(['change'])

const hostEl = ref(null)
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

async function exportPng() {
  if (!elements.length) return ElMessage.warning('画布是空的')
  const blob = await exportToBlob({
    elements,
    appState: { ...appState, exportWithDarkMode: false },
    files,
    mimeType: 'image/png',
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${document.title || 'whiteboard'}.png`
  a.click()
  URL.revokeObjectURL(a.href)
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
  }))
})

onBeforeUnmount(() => {
  clearTimeout(emitTimer)
  // 异步卸载，避免 React 18+ 同步 unmount 告警
  Promise.resolve().then(() => root?.unmount())
})

defineExpose({ getContent, exportPng })
</script>

<style scoped>
.react-host { height: 100%; }
</style>
