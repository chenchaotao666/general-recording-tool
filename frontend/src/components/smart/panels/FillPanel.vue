<template>
  <!-- 填色面板（§5.5）：规则行 = 字段 + 运算符 + 值 → 颜色；条件不完整不生效不计数。
       草稿模式：面板内自由编辑，点「确定」才落库 -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="460">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head"><b>填色</b></div>
      <div v-for="(r, i) in draft" :key="r.id || i" class="rule-row">
        <el-select :teleported="false" :model-value="r.fieldId" size="small" class="r-field" placeholder="字段"
                   @change="(v) => update(i, { fieldId: v, value: undefined })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-select :teleported="false" :model-value="r.operator" size="small" class="r-op"
                   @change="(v) => update(i, { operator: v })">
          <el-option v-for="op in opsOf(r)" :key="op" :value="op" :label="OP_LABELS[op]" />
        </el-select>
        <ConditionValue v-if="!NO_VALUE_OPS.includes(r.operator)" :field="fieldOf(r)"
                        :operator="r.operator" :value="r.value" @update="(v) => update(i, { value: v })" />
        <span class="arrow">→</span>
        <el-color-picker :model-value="r.color" size="small" @change="(v) => update(i, { color: v })" />
        <span class="r-del" @click="remove(i)">⊖</span>
      </div>
      <el-button link type="primary" size="small" @click="add">＋ 添加条件</el-button>
      <div class="panel-foot">
        <el-button size="small" @click="cancel">取消</el-button>
        <el-button size="small" type="primary" @click="confirm">确定</el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import ConditionValue from './ConditionValue.vue'
import { filterOpsOf, OP_LABELS, NO_VALUE_OPS } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  rules: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

// 草稿：打开时从 props 复制，确定才 emit（一次落库，避免防抖保存吞掉不完整行）
const draft = ref([])
watch(() => props.visible, (v) => {
  if (v) draft.value = props.rules.map((r) => ({ ...r }))
})

function fieldOf(r) { return props.fields.find(f => f.field_name === r.fieldId) }
function opsOf(r) { return fieldOf(r) ? filterOpsOf(fieldOf(r)) : [] }
function update(i, patch) { draft.value = draft.value.map((r, j) => (j === i ? { ...r, ...patch } : r)) }
function add() {
  draft.value = [...draft.value, { id: `f_${Date.now()}`, fieldId: null, operator: 'contains', value: undefined, color: '#fef9e0', order: draft.value.length }]
}
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i) }

function cancel() { emit('update:visible', false) }
function confirm() {
  emit('change', draft.value.filter((r) => r.fieldId))
  emit('update:visible', false)
}
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-foot { display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid #ebeef5; padding-top: 8px; }
.rule-row { display: flex; align-items: center; gap: 6px; }
.r-field { width: 120px; }
.r-op { width: 90px; }
.arrow { color: var(--el-text-color-placeholder); }
.r-del { cursor: pointer; color: var(--el-color-danger); }
</style>
