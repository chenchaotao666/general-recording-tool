<template>
  <component :is="decorative ? 'span' : 'button'" class="st-dd cell-dropdown"
    :class="{ up: open, open, 'cell-dropdown-hidden': !visible, 'cell-dropdown-decorative': decorative,
      'cell-dropdown-overlay': overlay, 'cell-dropdown-bordered': bordered, 'cell-dropdown-flush': flush }"
    :type="decorative ? undefined : 'button'" :disabled="decorative ? undefined : disabled"
    :tabindex="decorative ? undefined : visible ? 0 : -1"
    :aria-hidden="decorative || !visible ? true : undefined"
    :aria-label="decorative ? undefined : label" :aria-expanded="decorative ? undefined : open"
    @mousedown="stop" @dblclick="stop" @click="click" />
</template>
<script setup>
const props = defineProps({ open: Boolean, visible: { type: Boolean, default: true }, disabled: Boolean,
  label: { type: String, default: '展开或收起' }, decorative: Boolean, overlay: Boolean, bordered: Boolean, flush: Boolean })
const emit = defineEmits(['click'])
function stop(event) { if (!props.decorative) event.stopPropagation() }
function click(event) {
  if (props.decorative) return
  event.stopPropagation()
  if (!props.disabled && props.visible) emit('click', event)
}
</script>
<style scoped>
.cell-dropdown.st-dd { display: inline-flex; align-items: center; justify-content: center; flex: none; width: 24px; height: 24px;
  padding: 0; border: 0; border-radius: 4px; box-sizing: border-box; color: #808792; background: transparent; appearance: none; cursor: pointer; }
.cell-dropdown::before { content: ''; width: 0; height: 0; border-left: 3.5px solid transparent; border-right: 3.5px solid transparent; border-top: 5px solid currentColor; }
.cell-dropdown.up::before { border-top: 0; border-bottom: 5px solid currentColor; }
.cell-dropdown:hover, .cell-dropdown:focus-visible, .cell-dropdown.open { background: #E6E8E8; color: #808792; }
.cell-dropdown:focus-visible { outline: 1px solid var(--st-primary, #3370ff); outline-offset: -1px; }
.cell-dropdown.cell-dropdown-hidden { visibility: hidden; pointer-events: none; }
.cell-dropdown:disabled { opacity: .45; cursor: not-allowed; background: transparent; }
.cell-dropdown-decorative { pointer-events: none; }
/* 普通单元格内容区左右留白 8px；带 2px 选中边框的锚点直接占满单元格。
   两种容器都将箭头放在单元格顶部/右侧 6px，调用方不再单独设置偏移。 */
.cell-dropdown-overlay { position: absolute; top: 6px; right: -2px; z-index: 1; }
.cell-dropdown-overlay.cell-dropdown-bordered { top: 4px; right: 4px; }
.cell-dropdown-overlay.cell-dropdown-flush { top: 6px; right: 6px; }
</style>
