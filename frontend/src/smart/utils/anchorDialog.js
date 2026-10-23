import { nextTick, onBeforeUnmount, onMounted, watch } from 'vue'

const margin = 12
const maxWidth = 'calc(100vw - 24px)'
// el-dialog 默认顶部留白为 15vh；保留居中布局，同时为底部留出安全距离。
const centeredMaxHeight = 'calc(100vh - var(--el-dialog-margin-top, 15vh) - 12px)'

function clampPosition(value, size, viewport) {
  return Math.max(margin, Math.min(value, viewport - size - margin))
}

// 字段/编组编辑统一使用非模态 el-dialog：无遮罩且可穿透，表格仍可滚动/点击。
// at = { x, y }（clientX/Y）时锚定在触发点附近并限制在视口内；不传则保持默认居中位置。
export function anchoredDialogAttrs(at, width = 480, estHeight = 460) {
  const attrs = {
    modal: false,
    modalClass: 'st-nonmodal-overlay',
    modalPenetrable: true,
    closeOnClickModal: false,
    lockScroll: false,
    style: { maxWidth, maxHeight: centeredMaxHeight, overflowY: 'auto' },
  }
  if (!at) return attrs
  const left = Math.max(margin, Math.min(at.x + 4, window.innerWidth - width - margin))
  const top = Math.max(margin, Math.min(at.y + 4, window.innerHeight - estHeight - margin))
  return {
    ...attrs,
    class: 'st-at-dialog',
    // 初始坐标与运行时 left/top 分开，表单重新渲染不会覆盖避让/拖动后的坐标。
    style: { ...attrs.style, '--st-dialog-left': `${left}px`, '--st-dialog-top': `${top}px`,
      maxHeight: `max(0px, calc(100vh - ${(at.placement === 'button' ? margin : top) + margin}px))` },
  }
}

// 打开、内容变化和窗口缩放时按实际尺寸避让边界；拖动后只修正越界位置。
export function useButtonAnchoredDialog(getBody, getAt, isOpen) {
  let observer
  let observation = 0
  let positionedPanel
  let positionedAt
  function place() {
    const at = getAt()
    const panel = getBody()?.closest('.el-dialog')
    if (!isOpen() || !panel) return
    const dragged = !!panel.dataset.panelDragged
    panel.style.maxWidth = maxWidth
    panel.style.overflowY = 'auto'
    panel.style.maxHeight = !at && !dragged
      ? centeredMaxHeight : `${Math.max(0, window.innerHeight - margin * 2)}px`
    // 无锚点继续由 el-dialog 管理居中和顶部留白。
    if (!at && !dragged) return
    // offset 不受 el-dialog 入场 transform 影响，避免动画期间反复累加偏移。
    const rect = { width: panel.offsetWidth, height: panel.offsetHeight }
    let left = panel.offsetLeft
    let top = panel.offsetTop
    if (at?.placement === 'button' && !dragged) {
      const below = at.bottom + 6
      const above = at.top - rect.height - 6
      left = at.x
      top = below + rect.height <= window.innerHeight - margin ? below
        : above >= margin ? above : below
    }
    panel.style.left = `${clampPosition(left, rect.width, window.innerWidth)}px`
    panel.style.top = `${clampPosition(top, rect.height, window.innerHeight)}px`
  }
  async function observe() {
    const current = ++observation
    observer?.disconnect()
    await nextTick()
    const body = getBody()
    const panel = body?.closest('.el-dialog')
    if (current !== observation) return
    if (!isOpen() || !panel) { positionedPanel = null; return }
    const at = getAt()
    if (panel !== positionedPanel || at !== positionedAt) {
      if (!panel.dataset.panelDragged) {
        panel.style.removeProperty('left')
        panel.style.removeProperty('top')
      }
      positionedPanel = panel
      positionedAt = at
    }
    place()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(place)
      observer.observe(body)
      if (panel !== body) observer.observe(panel)
    }
  }
  watch([isOpen, getAt], observe, { flush: 'post' })
  onMounted(() => window.addEventListener('resize', place))
  onBeforeUnmount(() => {
    ++observation
    observer?.disconnect()
    window.removeEventListener('resize', place)
  })
  return observe
}

// 非模态没有遮罩，点击编辑框及其浮层以外区域时关闭。
// 使用捕获阶段，避免触发「打开」的那次 click 冒泡到 document 后又立刻关闭。
export function useNonModalOutsideClose(isOpen, close) {
  const onDocClick = (e) => {
    if (!isOpen()) return
    if (e.target.closest?.('.el-dialog, .el-popper, .el-message-box, .el-overlay')) return
    close()
  }
  onMounted(() => document.addEventListener('click', onDocClick, true))
  onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))
}
