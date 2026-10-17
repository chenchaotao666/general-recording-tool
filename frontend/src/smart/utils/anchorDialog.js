import { onBeforeUnmount, onMounted } from 'vue'

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
    style: { left: `${left}px`, top: `${top}px`, maxHeight: `${window.innerHeight - top - margin}px` },
  }
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
