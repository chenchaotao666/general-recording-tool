<template>
  <!-- 列头：类型图标 + 字段名 + 筛选态漏斗 + 排序标记 + 菜单触发（点击或右键） -->
  <span class="field-head" @contextmenu.prevent.stop="$emit('menu', $event)">
    <StIcon :name="field.field_type" :size="14" class="field-icon" />
    <span class="field-name">{{ field.label }}</span>
    <StIcon v-if="filtered" name="filter" :size="12" class="filter-dot" />
    <StIcon v-if="sortMark" :name="sortMark" :size="12" class="sort-mark" />
    <span class="head-menu" @click.stop="$emit('menu', $event)"><StIcon name="caret-down" :size="12" /></span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import StIcon from '../icons/StIcon.vue'

const props = defineProps({ field: Object, view: Object })
defineEmits(['menu'])

const filtered = computed(() =>
  (props.view?.config?.filters?.conditions || []).some(c => c.fieldId === props.field.field_name))
const sortMark = computed(() => {
  const s = (props.view?.config?.sorts || []).find(x => x.fieldId === props.field.field_name)
  return s ? (s.direction === 'desc' ? 'caret-down' : 'caret-up') : ''
})
</script>

<style scoped>
.field-head { display: inline-flex; align-items: center; gap: 5px; width: 100%; }
.field-icon { color: var(--st-text-2); flex: none; }
/* 表头字体（设计稿 PixPin_2026-10-15_00-04-29）：13px 半Bold 灰色，与图标同色调 */
.field-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 13px; font-weight: 600; color: var(--st-text-2);
}
.filter-dot, .sort-mark { color: var(--st-primary); }
.head-menu { margin-left: auto; color: var(--st-text-3); padding: 0 2px; cursor: pointer; display: inline-flex; }
.head-menu:hover { color: var(--st-primary); }
</style>
