<template>
  <!-- 记录详情面板（参照 docs/智慧表格/右侧-详细信息.png）：停靠在表格右侧、占位（表格让出宽度，不遮挡）。
       顶栏 |→ 收起 + ∧∨ 上一条/下一条；卡片内标题（主字段值）+ ⋯（生成记录副本 / 删除记录）；
       字段两列：类型图标 + 字段名 | 值。编组为可折叠节（∨ 组名，成员带竖向层级线）。
       值默认展示态，空值显示灰色占位提示；单击可编辑的值进入编辑器（复用单元格编辑器） -->
  <aside class="rd-panel st-side-panel" :style="{ width: `${panelWidth}px` }">
    <!-- 左边框拖拽改宽度（宽度记在本机，下次打开沿用） -->
    <div class="st-side-resize" :class="{ active: resizing }" data-smart-tip="拖动调整宽度" @mousedown.prevent="startResize" />
    <slot name="header"><div class="rd-top">
      <button class="rd-ico st-icon-action" data-smart-tip="收起" @click="$emit('close')"><StIcon name="panel-close" :size="18" /></button>
      <span class="rd-nav">
        <button class="rd-ico st-icon-action" data-smart-tip="上一条" :disabled="!hasPrev" @click="$emit('nav', -1)"><StIcon name="chevron-up" :size="18" /></button>
        <button class="rd-ico st-icon-action" data-smart-tip="下一条" :disabled="!hasNext" @click="$emit('nav', 1)"><StIcon name="chevron-down" :size="18" /></button>
      </span>
    </div></slot>
    <RecordDetailContent v-bind="$attrs" />
  </aside>
</template>

<script setup>
import RecordDetailContent from './RecordDetailContent.vue'
import StIcon from '../icons/StIcon.vue'
import { usePanelResize } from '../../../smart/utils/usePanelResize.js'
defineOptions({ inheritAttrs: false })
defineProps({ hasPrev: Boolean, hasNext: Boolean })
defineEmits(['close', 'nav'])
const { panelWidth, resizing, startResize } = usePanelResize('st-record-panel-width', 560)
</script>

<style scoped>
.rd-panel { position: relative; display: flex; flex-direction: column; flex: none; min-height: 0; padding: 0 12px 12px 12px;
            box-sizing: border-box; background: #fff; overflow: hidden; max-width: 100%; }
.rd-top { display: flex; align-items: center; justify-content: space-between; height: 44px; flex: none; padding: 0 2px 0 6px; border-bottom: 1px solid var(--st-border); }
.rd-nav { display: inline-flex; gap: 4px; }
.rd-ico { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; padding: 0;
          border: none; background: transparent; border-radius: 6px; color: var(--st-text-1); cursor: pointer; }
.rd-ico:hover:not(:disabled) { background: var(--st-bg-hover); }
.rd-ico:disabled { color: var(--st-disabled); cursor: not-allowed; }
</style>
