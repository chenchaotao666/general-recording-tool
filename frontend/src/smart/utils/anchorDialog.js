import { nextTick, onBeforeUnmount, onMounted, watch } from 'vue'

// 字段/编组编辑统一使用非模态 el-dialog：无遮罩且可穿透，表格仍可滚动/点击。
// at = { x, y }（clientX/Y）时锚定在触发点附近并限制在视口内；不传则保持默认居中位置。
export function anchoredDialogAttrs(at, width = 480, estHeight = 460) {
  const attrs = {
    modal: false,
    modalPenetrable: true,
    closeOnClickModal: false,
    lockScroll: false,
  }
  if (!at) return attrs
  const margin = 12
  const left = Math.max(margin, Math.min(at.x + 4, window.innerWidth - width - margin))
  const top = Math.max(margin, Math.min(at.y + 4, window.innerHeight - estHeight - margin))
  return {
    ...attrs,
    class: 'st-at-dialog',
    style: { left: `${left}px`, top: `${top}px`, maxWidth: 'calc(100vw - 24px)',
      maxHeight: `${window.innerHeight - (at.placement === 'button' ? margin : top) - margin}px` },
  }
}

// 按内容实际高度定位按钮触发的面板；字段类型切换、窗口缩放后重新避让边界。
export function useButtonAnchoredDialog(getBody, getAt, isOpen) {
  let observer
  function place() {
    const at = getAt()
    const panel = getBody()?.closest('.el-dialog')
    if (!isOpen() || at?.placement !== 'button' || !panel) return
    const margin = 12
    panel.style.maxHeight = `${window.innerHeight - margin * 2}px`
    const rect = panel.getBoundingClientRect()
    const below = at.bottom + 6
    const above = at.top - rect.height - 6
    const top = below + rect.height <= window.innerHeight - margin ? below
      : above >= margin ? above : Math.max(margin, Math.min(below, window.innerHeight - rect.height - margin))
    panel.style.left = `${Math.max(margin, Math.min(at.x, window.innerWidth - rect.width - margin))}px`
    panel.style.top = `${top}px`
  }
  async function observe() {
    observer?.disconnect()
    await nextTick()
    if (!isOpen() || !getBody()) return
    place()
    observer = new ResizeObserver(place)
    observer.observe(getBody())
  }
  watch([isOpen, getAt], observe, { flush: 'post' })
  onMounted(() => window.addEventListener('resize', place))
  onBeforeUnmount(() => { observer?.disconnect(); window.removeEventListener('resize', place) })
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
