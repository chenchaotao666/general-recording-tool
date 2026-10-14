<template>
  <!-- 列头：类型图标 + 字段名 + 筛选态漏斗 + 排序标记 + 菜单触发（▾ 点击或右键） -->
  <span class="field-head" @contextmenu.prevent.stop="$emit('menu', $event)">
    <span class="field-icon" v-html="svgIcon" />
    <span class="field-name">{{ field.label }}</span>
    <span v-if="filtered" class="filter-dot">⧩</span>
    <span class="sort-mark">{{ sortMark }}</span>
    <span class="head-menu" @click.stop="$emit('menu', $event)">▾</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { fieldTypeIconSvg } from '../../../smart/registry/fieldIcons.js'

const props = defineProps({ field: Object, view: Object })
defineEmits(['menu'])

const svgIcon = computed(() => fieldTypeIconSvg(props.field.field_type))
const filtered = computed(() =>
  (props.view?.config?.filters?.conditions || []).some(c => c.fieldId === props.field.field_name))
const sortMark = computed(() => {
  const s = (props.view?.config?.sorts || []).find(x => x.fieldId === props.field.field_name)
  return s ? (s.direction === 'desc' ? '↓' : '↑') : ''
})
</script>

<style scoped>
.field-head { display: inline-flex; align-items: center; gap: 5px; width: 100%; }
.field-icon { display: inline-flex; align-items: center; color: var(--el-text-color-secondary); flex: none; }
/* 表头字体（设计稿 PixPin_2026-10-15_00-04-29）：13px 半Bold 灰色，与图标同色调 */
.field-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary);
}
.filter-dot, .sort-mark { color: var(--el-color-primary); font-size: 12px; }
.head-menu { margin-left: auto; color: var(--el-text-color-placeholder); padding: 0 2px; cursor: pointer; font-size: 12px; }
.head-menu:hover { color: var(--el-color-primary); }
</style>
