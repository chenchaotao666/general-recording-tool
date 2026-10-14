<template>
  <!-- 排序面板（§5.3）：多级排序规则 + 方向按钮组（类型自适应文案）+ 自动排序开关 -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="380">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head">
        <b>排序</b>
        <el-checkbox :model-value="autoSort" size="small" @change="$emit('auto-sort', $event)">自动排序</el-checkbox>
      </div>
      <div v-for="(s, i) in sorts" :key="i" class="rule-row">
        <el-select :teleported="false" :model-value="s.fieldId" size="small" class="r-field"
                   @change="(v) => update(i, { fieldId: v })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-radio-group :model-value="s.direction" size="small" @change="(v) => update(i, { direction: v })">
          <el-radio-button value="asc">{{ labelsOf(s)[0] }}</el-radio-button>
          <el-radio-button value="desc">{{ labelsOf(s)[1] }}</el-radio-button>
        </el-radio-group>
        <span class="r-del" @click="remove(i)">⊖</span>
      </div>
      <el-button link type="primary" size="small" @click="add">＋ 添加排序字段</el-button>
    </div>
  </el-popover>
</template>

<script setup>
import { computed } from 'vue'
import { sortDirectionLabels } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  sorts: { type: Array, default: () => [] },
  autoSort: { type: Boolean, default: true },
})
const emit = defineEmits(['update:visible', 'change', 'auto-sort'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

function labelsOf(s) {
  return sortDirectionLabels(props.fields.find(f => f.field_name === s.fieldId))
}
function update(i, patch) { emit('change', props.sorts.map((s, j) => (j === i ? { ...s, ...patch } : s))) }
function add() { emit('change', [...props.sorts, { fieldId: props.fields[0]?.field_name, direction: 'asc' }]) }
function remove(i) { emit('change', props.sorts.filter((_, j) => j !== i)) }
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.rule-row { display: flex; align-items: center; gap: 6px; }
.r-field { width: 140px; }
.r-del { cursor: pointer; color: var(--el-color-danger); }
</style>
