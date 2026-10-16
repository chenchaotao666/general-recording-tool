<template>
  <!-- 记录详情抽屉（对齐参照 单元格右键菜单-展开此记录.png）：
       640px 宽；上一条/下一条；字段两列布局；编组为可折叠节（组名 + 缩进成员） -->
  <el-drawer v-model="visibleModel" :title="title" size="640px" class="record-detail">
    <div v-if="record" class="detail">
      <div class="nav">
        <el-button size="small" :disabled="!hasPrev" @click="$emit('nav', -1)">∧ 上一条</el-button>
        <el-button size="small" :disabled="!hasNext" @click="$emit('nav', 1)">∨ 下一条</el-button>
      </div>
      <template v-for="row in rows" :key="row.key">
        <!-- 编组节：可折叠 -->
        <div v-if="row.group" class="d-group" @click="toggle(row.group.id)">
          <StIcon :name="collapsed.has(row.group.id) ? 'chevron-right' : 'chevron-down'" :size="13" class="dg-caret" />
          <span class="dg-name">{{ row.group.name }}</span>
        </div>
        <template v-if="row.group ? !collapsed.has(row.group.id) : true">
          <div v-for="f in row.fields" :key="f.field_name" class="d-row" :class="{ member: !!row.group }">
            <div class="d-label"><StIcon :name="f.field_type" :size="14" class="d-icon" />{{ f.label }}</div>
            <div class="d-value">
              <SmartCell v-if="regOf(f).readonly" :field="f" :record="record" />
              <component v-else :is="editorFor(f)" :field="f" :record="record"
                         @commit="(v) => $emit('cell-commit', { row: record, field: f, value: v })" />
            </div>
          </div>
        </template>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref } from 'vue'
import SmartCell from '../grid/SmartCell.vue'
import SmartCellEditor from '../grid/SmartCellEditor.vue'
import StIcon from '../icons/StIcon.vue'
import { regOf } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  record: Object,
  fields: { type: Array, default: () => [] },
  columnGroups: { type: Array, default: () => [] },
  hasPrev: Boolean,
  hasNext: Boolean,
})
const emit = defineEmits(['close', 'nav', 'cell-commit', 'update:visible'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

const title = computed(() => {
  if (!props.record) return ''
  const first = props.fields[0]
  return props.record[first?.field_name] || `#${props.record.id}`
})
const editorFor = () => SmartCellEditor

// 字段行序列：散列字段 + 编组节（保持字段顺序，编组内字段聚合到组下）
const rows = computed(() => {
  const gs = props.columnGroups.filter(g => (g.field_names || []).length)
  const emitted = new Set()
  const out = []
  for (const f of props.fields) {
    const g = gs.find(x => x.field_names.includes(f.field_name))
    if (!g) out.push({ key: f.field_name, fields: [f] })
    else if (!emitted.has(g.id)) {
      emitted.add(g.id)
      out.push({ key: `g_${g.id}`, group: g, fields: props.fields.filter(x => g.field_names.includes(x.field_name)) })
    }
  }
  return out
})
const collapsed = ref(new Set())
function toggle(id) {
  const s = new Set(collapsed.value)
  s.has(id) ? s.delete(id) : s.add(id)
  collapsed.value = s
}
</script>

<style scoped>
.detail { display: flex; flex-direction: column; gap: 4px; }
.nav { display: flex; gap: 8px; margin-bottom: 8px; }
.d-row { display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--st-border); }
.d-row.member { padding-left: 22px; border-left: 1px solid var(--st-border); margin-left: 6px; }
.d-group { display: flex; align-items: center; gap: 6px; padding: 8px 0 4px; cursor: pointer; font-weight: 600; font-size: 13px; color: var(--st-text-1); }
.dg-caret { color: var(--st-text-3); }
.d-label { width: 180px; flex: none; color: var(--st-text-2); font-size: 13px; display: flex; gap: 6px; align-items: center; }
.d-icon { color: var(--st-text-2); flex: none; }
.d-value { flex: 1; min-width: 0; }
</style>
