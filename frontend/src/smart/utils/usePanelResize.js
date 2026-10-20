import { onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'

// 右侧嵌入面板共用：拖左边缘改宽度，关闭/切页时清理拖动状态。
export function usePanelResize(storageKey, defaultWidth) {
  const clamp = width => Math.min(Math.max(400, Math.round(window.innerWidth * 0.7)),
    Math.max(400, Math.round(width)))
  let initial = defaultWidth
  try {
    const saved = Number(localStorage.getItem(storageKey))
    if (Number.isFinite(saved) && saved > 0) initial = saved
  } catch { /* 存储不可用时使用默认宽度 */ }
  const panelWidth = ref(clamp(initial))
  const resizing = ref(false)
  let cleanup = null
  function stopResize() { cleanup?.() }
  function startResize(event) {
    if (event.button !== 0) return
    stopResize()
    const startX = event.clientX
    const startWidth = panelWidth.value
    const { cursor, userSelect } = document.body.style
    resizing.value = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    const move = e => { panelWidth.value = clamp(startWidth + startX - e.clientX) }
    cleanup = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', stopResize)
      window.removeEventListener('blur', stopResize)
      document.body.style.cursor = cursor
      document.body.style.userSelect = userSelect
      resizing.value = false
      cleanup = null
      try { localStorage.setItem(storageKey, String(panelWidth.value)) } catch { /* 只本次生效 */ }
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', stopResize)
    window.addEventListener('blur', stopResize)
  }
  const fit = () => { panelWidth.value = clamp(panelWidth.value) }
  onMounted(() => window.addEventListener('resize', fit))
  onDeactivated(stopResize)
  onBeforeUnmount(() => {
    stopResize()
    window.removeEventListener('resize', fit)
  })
  return { panelWidth, resizing, startResize, stopResize }
}
