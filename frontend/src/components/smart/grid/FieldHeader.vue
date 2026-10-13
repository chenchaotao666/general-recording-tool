<template>
  <!-- 列头：类型图标 + 字段名 + 筛选态漏斗 + 排序标记 + 菜单触发（▾ 点击或右键） -->
  <span class="field-head" @contextmenu.prevent.stop="$emit('menu', $event)">
    <span class="field-icon">{{ icon }}</span>
    <span class="field-name">{{ field.label }}</span>
    <span v-if="filtered" class="filter-dot">⧩</span>
    <span class="sort-mark">{{ sortMark }}</span>
    <span class="head-menu" @click.stop="$emit('menu', $event)">▾</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ field: Object, view: Object })
defineEmits(['menu'])

const ICONS = {
  text: 'A', singleSelect: '⊙', multiSelect: '☰', number: '₁₂₃', percent: '%', currency: '¥',
  date: '📅', checkbox: '☑', url: '🔗', phone: '📞', email: '✉', member: '👤', progress: '▱',
  image: '🖼', file: '📁', autoNumber: '1⇓', relation: '🔗⇢', lookup: '🧾', formula: 'fx',
  createdBy: '👤', lastModifiedBy: '👤', createdTime: '📅', lastModifiedTime: '📅',
}
const icon = computed(() => ICONS[props.field.field_type] || 'A')
const filtered = computed(() =>
  (props.view?.config?.filters?.conditions || []).some(c => c.fieldId === props.field.field_name))
const sortMark = computed(() => {
  const s = (props.view?.config?.sorts || []).find(x => x.fieldId === props.field.field_name)
  return s ? (s.direction === 'desc' ? '↓' : '↑') : ''
})
</script>

<style scoped>
.field-head { display: inline-flex; align-items: center; gap: 4px; width: 100%; }
.field-icon { color: var(--el-color-primary); font-size: 12px; min-width: 16px; text-align: center; }
.field-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.filter-dot, .sort-mark { color: var(--el-color-primary); }
.head-menu { margin-left: auto; color: var(--el-text-color-placeholder); padding: 0 2px; cursor: pointer; }
.head-menu:hover { color: var(--el-color-primary); }
</style>
