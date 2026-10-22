<template>
  <!-- 列头（参照 docs/智慧表格/表头样式.png）：类型图标 + 字段名 + AI 角标 + 筛选态漏斗 + 下拉菜单（不显示排序标记）。
       字段名有空间就换行完整显示（行数上限 = 表头可用高度能放下的行数），放不下才省略；
       下拉三角在 hover 列头或单击选中列时显示（统一 .st-dd 交互）。点击三角或右键出菜单 -->
  <span class="field-head" @contextmenu.prevent.stop="$emit('menu', $event)">
    <StIcon :name="iconName" :size="14" class="field-icon" />
    <!-- AI 角标、筛选漏斗内联在字段名文字流末尾：紧跟最后一个字（字段名换行时也不会被推到最右侧） -->
    <span class="field-name" :style="{ '-webkit-line-clamp': lines }">{{ field.label }}<AiBadge v-if="isAi" class="ai-badge" /><span
      v-if="filtered" class="filter-dot st-icon-action" aria-label="编辑该列筛选" @click.stop="onFilterClick" @dblclick.stop><StIcon name="filter" :size="15" /></span></span>
    <CellDropdown class="head-menu" :open="menuOpen" label="列菜单" @click="$emit('menu', $event)" />
  </span>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { isCondValueEmpty } from '../../../smart/utils/format.js'
import { computed } from 'vue'
import StIcon from '../icons/StIcon.vue'
import AiBadge from '../ai/AiBadge.vue'
import CellDropdown from './CellDropdown.vue'

const props = defineProps({
  field: Object,
  view: Object,
  lines: { type: Number, default: 2 },   // 字段名最多显示几行（超出省略）
  readonly: { type: Boolean, default: false },
  menuOpen: { type: Boolean, default: false },   // 列头菜单展开中：三角保持「展开」底色（与单元格下拉同一套状态）
})
const emit = defineEmits(['menu', 'filter'])
function onFilterClick(e) {
  const th = e.currentTarget.closest('th') || e.currentTarget
  emit('filter', th.getBoundingClientRect())
}

// AI 字段：图标按输出类型；列头带 AI✦ 角标（生成按钮在选中列时浮在列右侧，见 SmartGrid / AiRunButton）
const isAi = computed(() => props.field.field_type === 'ai')
const iconName = computed(() => fieldIconName(props.field))

// 只有生效的条件才显示漏斗（固定到工具栏但还没填值的不算）
const filtered = computed(() => (props.view?.config?.filters?.conditions || []).some(c => c.fieldId === props.field.field_name
  && (['isEmpty', 'isNotEmpty'].includes(c.operator) || !isCondValueEmpty(c.value))))
</script>

<style scoped>
/* 顶对齐：多行字段名与同排单行字段名首行对齐（参照图「单位-计数-计算排名」） */
.field-head { display: flex; align-items: flex-start; gap: 5px; width: 100%; min-width: 0; position: relative; box-sizing: border-box; }
.field-icon { color: var(--st-head-text); flex: none; margin-top: 4px; }
/* 表头字体统一：13px 粗体灰（编组标题同款） */
.field-name {
  flex: 0 1 auto; min-width: 0; overflow: hidden;
  display: -webkit-box; -webkit-box-orient: vertical;
  white-space: normal; word-break: break-all; text-overflow: ellipsis;
  font-size: var(--st-font-size); line-height: 20px; font-weight: 600; color: var(--st-head-text);
}
.filter-dot { display: inline-flex; vertical-align: -4px; margin-left: 4px; color: var(--st-primary); padding: 2px; border-radius: 4px; cursor: pointer; }
.filter-dot:hover { background: rgba(46, 107, 230, .12); }
/* 下拉按钮：默认隐藏，hover / 单击选中列 / 菜单展开时出现；外观与单元格单选/多选的下拉按钮一致——
   常态只有灰三角（无底色），hover 按钮本身出现浅灰圆角方块（#E6E8E8，参照 PixPin_2026-10-17_17-37-46）。
   右缘对齐内容区（不能越出：.vxe-cell--title 裁剪，越出部分会被遮住） */
.head-menu { position: absolute; right: 0; top: -2px; visibility: hidden; }   /* 竖直方向与字段名首行居中对齐（20px 行高 vs 24px 按钮）*/
.head-menu.open { visibility: visible; }
.ai-badge { display: inline-flex; vertical-align: 1px; margin-left: 4px; }
</style>
