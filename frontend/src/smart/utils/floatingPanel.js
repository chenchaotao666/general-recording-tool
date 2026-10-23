import { nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useZIndex } from 'element-plus'

// 自定义浮层与 Element Plus 共用层级序列；内容变化、缩窗后按实际尺寸避让。
export function useFloatingPanel(getPanel, getLayer = getPanel) {
  const { nextZIndex } = useZIndex()
  let observer, frame = 0, revision = 0, disposed = false
  function fit() {
    const panel = getPanel()
    if (!panel?.isConnected || !panel.getClientRects().length) return
    const width = window.innerWidth, height = window.innerHeight
    panel.style.maxWidth = `${Math.max(0, width - 24)}px`
    panel.style.maxHeight = `${Math.max(0, height - 24)}px`
    const rect = panel.getBoundingClientRect()
    const left = Math.max(12, Math.min(rect.left, width - rect.width - 12))
    const top = Math.max(12, Math.min(rect.top, height - rect.height - 12))
    if (Math.abs(left - rect.left) > .5 || Math.abs(top - rect.top) > .5) {
      Object.assign(panel.style, { position: 'fixed', margin: '0', transform: 'none', left: `${left}px`, top: `${top}px` })
    }
  }
  const schedule = () => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(fit)
  }
  async function refresh() {
    const current = ++revision
    await nextTick()
    if (disposed || current !== revision) return
    observer?.disconnect()
    const panel = getPanel(), layer = getLayer()
    if (!panel) return
    if (layer) layer.style.zIndex = String(nextZIndex())
    fit()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(schedule)
      observer.observe(panel)
    }
  }
  onMounted(() => {
    refresh()
    window.addEventListener('resize', schedule)
    window.visualViewport?.addEventListener('resize', schedule)
  })
  onBeforeUnmount(() => {
    disposed = true
    ++revision
    observer?.disconnect()
    cancelAnimationFrame(frame)
    window.removeEventListener('resize', schedule)
    window.visualViewport?.removeEventListener('resize', schedule)
  })
  return refresh
}
