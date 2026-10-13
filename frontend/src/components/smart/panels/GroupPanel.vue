<template>
  <!-- 分组面板（§5.2）：多级分组字段列表 + 方向（类型自适应文案） -->
  <el-popover v-model:visible="visibleModel" placement="bottom-start" :width="380">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head"><b>分组</b></div>
      <div v-for="(g, i) in groups" :key="i" class="rule-row">
        <span class="drag">⋮⋮</span>
        <el-select :teleported="false" :model-value="g.fieldId" size="small" class="r-field" placeholder="选择分组字段"
                   @change="(v) => update(i, { fieldId: v })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-radio-group :model-value="g.direction" size="small" @change="(v) => update(i, { direction: v })">
          <el-radio-button value="asc">{{ labelsOf(g)[0] }}</el-radio-button>
          <el-radio-button value="desc">{{ labelsOf(g)[1] }}</el-radio-button>
        </el-radio-group>
        <span class="r-del" @click="remove(i)">⊖</span>
      </div>
      <el-button link type="primary" size="small" :disabled="groups.length >= 3" @click="add">
        ＋ 添加分组字段{{ groups.length >= 3 ? '（最多 3 级）' : '' }}
      </el-button>
    </div>
  </el-popover>
</template>

<script setup>
import { computed } from 'vue'
import { sortDirectionLabels } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

function labelsOf(g) {
  return sortDirectionLabels(props.fields.find(f => f.field_name === g.fieldId))
}
function update(i, patch) { emit('change', props.groups.map((g, j) => (j === i ? { ...g, ...patch } : g))) }
function add() { emit('change', [...props.groups, { fieldId: null, direction: 'asc' }]) }
function remove(i) { emit('change', props.groups.filter((_, j) => j !== i)) }
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.rule-row { display: flex; align-items: center; gap: 6px; }
.drag { color: var(--el-text-color-placeholder); cursor: grab; }
.r-field { width: 150px; }
.r-del { cursor: pointer; color: var(--el-color-danger); }
</style>
