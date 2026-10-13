<template>
  <!-- 筛选面板（设计文档 §5.1）：条件卡片列表 + 作用域切换（仅你可见/对所有人）+ pin 图钉 -->
  <el-popover v-model:visible="visibleModel" placement="bottom-start" :width="420" popper-class="filter-popover">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head">
        <b>筛选</b>
        <el-radio-group :model-value="scope" size="small" @change="$emit('scope-change', $event)">
          <el-radio-button value="personal">调整仅你可见</el-radio-button>
          <el-radio-button value="shared">对所有人生效</el-radio-button>
        </el-radio-group>
      </div>
      <div v-for="(c, i) in conditions" :key="c.id || i" class="cond-row">
        <el-select :teleported="false" :model-value="c.fieldId" size="small" class="c-field" placeholder="选择字段"
                   @change="(v) => update(i, { fieldId: v, operator: defaultOp(v), value: undefined })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-select :teleported="false" :model-value="c.operator" size="small" class="c-op" placeholder="条件"
                   @change="(v) => update(i, { operator: v })">
          <el-option v-for="op in opsOf(c)" :key="op" :value="op" :label="OP_LABELS[op]" />
        </el-select>
        <ConditionValue v-if="!NO_VALUE_OPS.includes(c.operator)" :field="fieldOf(c)"
                        :operator="c.operator" :value="c.value"
                        @update="(v) => update(i, { value: v })" />
        <span class="c-pin" :class="{ on: c.pinned }" title="固定到工具栏" @click="update(i, { pinned: !c.pinned })">📌</span>
        <span class="c-del" @click="remove(i)">⊖</span>
      </div>
      <el-button link type="primary" size="small" @click="add">＋ 添加筛选条件</el-button>
    </div>
  </el-popover>
</template>

<script setup>
import { computed } from 'vue'
import ConditionValue from './ConditionValue.vue'
import { filterOpsOf, OP_LABELS, NO_VALUE_OPS } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  conditions: { type: Array, default: () => [] },
  scope: { type: String, default: 'personal' },
})
const emit = defineEmits(['update:visible', 'change', 'scope-change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

function fieldOf(c) { return props.fields.find(f => f.field_name === c.fieldId) }
function opsOf(c) { return fieldOf(c) ? filterOpsOf(fieldOf(c)) : [] }
function defaultOp(fieldName) {
  const f = props.fields.find(x => x.field_name === fieldName)
  return f ? filterOpsOf(f)[0] : 'contains'
}
function update(i, patch) {
  const next = props.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c))
  emit('change', next)
}
function add() {
  emit('change', [...props.conditions, { id: `c_${Date.now()}`, fieldId: null, operator: 'contains', value: undefined, pinned: false }])
}
function remove(i) { emit('change', props.conditions.filter((_, j) => j !== i)) }
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.cond-row { display: flex; align-items: center; gap: 6px; }
.c-field { width: 130px; }
.c-op { width: 96px; }
.c-pin { cursor: pointer; opacity: 0.35; }
.c-pin.on { opacity: 1; }
.c-del { cursor: pointer; color: var(--el-color-danger); }
</style>
