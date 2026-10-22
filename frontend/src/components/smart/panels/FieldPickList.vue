<template>
  <!-- 「选择字段」列表（全表统一的字段选择面板，参照 docs/PixPin_2026-10-18_01-05-36.png）：
       灰色标题 + 字段按表格列序列出；列编组为可折叠节点（∨ 组名，成员缩进），编组信息与表头一致。
       添加筛选条件 / 筛选卡片切换字段 / 排序·分组·填色字段下拉（TbFieldSelect）共用 -->
  <div class="fpl">
    <div class="fpl-title">{{ title }}</div>
    <div class="fpl-list" :style="{ maxHeight: `${maxHeight}px` }">
      <template v-for="n in nodes" :key="n.key">
        <SmartListItem v-if="n.group" class="fpl-item fpl-group" @click="toggle(n.group.id)">
          <StIcon :name="collapsed.has(n.group.id) ? 'chevron-right' : 'chevron-down'" :size="14" class="fpl-caret" />
          <span class="fpl-name">{{ n.group.name }}</span>
        </SmartListItem>
        <template v-if="!n.group || !collapsed.has(n.group.id)">
          <SmartListItem v-for="f in n.fields" :key="f.field_name" class="fpl-item" :class="{ sub: !!n.group }" :selected="isSelected(f.field_name)"
               :role="multiple ? 'checkbox' : undefined" :aria-checked="multiple ? isSelected(f.field_name) : undefined"
               :tabindex="multiple ? 0 : undefined" :data-smart-tip="f.label" @click="emit('pick', f)"
               @keydown.enter.prevent="emit('pick', f)" @keydown.space.prevent="emit('pick', f)">
            <StIcon :name="fieldIconName(f)" :size="16" class="fpl-ico" /><span class="fpl-name">{{ f.label }}</span>
            <span v-if="multiple" class="fpl-check" :class="{ checked: isSelected(f.field_name) }" aria-hidden="true">{{ isSelected(f.field_name) ? '✓' : '' }}</span>
          </SmartListItem>
        </template>
      </template>
      <div v-if="!nodes.length" class="fpl-empty">没有可选字段</div>
    </div>
  </div>
</template>

<script setup>
import SmartListItem from '../common/SmartListItem.vue'
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, inject, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  // 编组：不传时取 SmartTablePage 提供的当前表编组（smartColumnGroups）
  columnGroups: { type: Array, default: null },
  selected: { type: [String, Array], default: null },   // 数组用于多选字段
  title: { type: String, default: '选择字段' },
  maxHeight: { type: Number, default: 420 },
})
const emit = defineEmits(['pick'])
const multiple = computed(() => Array.isArray(props.selected))
const isSelected = name => multiple.value ? props.selected.includes(name) : props.selected === name
const injectedGroups = inject('smartColumnGroups', ref([]))
const groupsSrc = computed(() => props.columnGroups ?? injectedGroups.value ?? [])

const collapsed = ref(new Set())
function toggle(id) {
  const s = new Set(collapsed.value)
  s.has(id) ? s.delete(id) : s.add(id)
  collapsed.value = s
}
// 与表头同构：散列字段 + 编组节（编组出现在其首个成员的位置；只列出 fields 中存在的成员）
const nodes = computed(() => {
  const groups = groupsSrc.value.filter(g => (g.field_names || []).length)
  const out = []
  const done = new Set()
  for (const f of props.fields) {
    const g = groups.find(x => x.field_names.includes(f.field_name))
    if (!g) out.push({ key: f.field_name, fields: [f] })
    else if (!done.has(g.id)) {
      done.add(g.id)
      out.push({ key: `g${g.id}`, group: g, fields: props.fields.filter(x => g.field_names.includes(x.field_name)) })
    }
  }
  return out
})
</script>

<style scoped>
/* 尺寸参照稿：标题 14px 灰；行 32px、字段名 15px、类型图标 16px 深色；编组成员再缩进一级；hover/选中浅灰圆角底 */
.fpl { width: 300px; }
.fpl-title { font-size: var(--st-font-size); color: var(--st-text-3); padding: 4px 12px 8px; }
.fpl-list { overflow-y: auto; }
.fpl-item { display: flex; align-items: center; padding: 0 8px 0 18px; cursor: pointer;
    }
.fpl-item.sub { padding-left: 44px; }
.fpl-group {  padding-left: 18px; }
.fpl-caret { color: var(--st-text-2); flex: none; }
.fpl-ico { color: var(--st-text-2); flex: none; }
.fpl-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fpl-empty { padding: 12px; font-size: var(--st-font-size); color: var(--st-text-3); text-align: center; }
.fpl-check { margin-left: auto; width: 16px; height: 16px; flex: none; box-sizing: border-box; border: 1px solid #d5d9df; border-radius: 3px; font-size: var(--st-font-size); line-height: 14px; text-align: center; }
.fpl-check.checked { background: var(--st-primary); border-color: var(--st-primary); color: #fff; }
.fpl-item:focus-visible { outline: 2px solid var(--st-primary); outline-offset: -2px; }
</style>
