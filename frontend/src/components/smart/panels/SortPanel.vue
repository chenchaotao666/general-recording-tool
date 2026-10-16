<template>
  <!-- 排序面板（§5.3）：多级排序规则 + 方向按钮组（类型自适应文案）+ 自动排序开关 -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="380">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head">
        <b>排序</b>
        <span class="auto-sort">
          <span class="as-label">自动排序</span>
          <el-switch :model-value="autoSort" size="small" @change="$emit('auto-sort', $event)" />
        </span>
      </div>
      <div v-for="(s, i) in sorts" :key="i" class="rule-row" :class="dropClass(i)"
           draggable="true" @dragstart="dragIdx = i" @dragover.prevent="overIdx = i"
           @drop.prevent="dropRow(i)" @dragend="dragIdx = overIdx = null">
        <span class="drag"><StIcon name="drag" :size="14" /></span>
        <el-select :teleported="false" :model-value="s.fieldId" size="small" class="r-field"
                   @change="(v) => update(i, { fieldId: v })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-radio-group :model-value="s.direction" size="small" @change="(v) => update(i, { direction: v })">
          <el-radio-button value="asc">{{ labelsOf(s)[0] }}</el-radio-button>
          <el-radio-button value="desc">{{ labelsOf(s)[1] }}</el-radio-button>
        </el-radio-group>
        <span class="r-del" title="删除" @click.stop="remove(i)"><StIcon name="minus-circle" :size="16" /></span>
      </div>
      <el-button link type="primary" size="small" @click="add">＋ 添加排序字段</el-button>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
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

// 拖拽排序：排序规则有优先级，顺序即语义（同 GroupPanel 交互）
const dragIdx = ref(null)
const overIdx = ref(null)
function dropClass(i) {
  if (dragIdx.value === null || overIdx.value !== i || dragIdx.value === i) return ''
  return dragIdx.value > i ? 'drop-before' : 'drop-after'
}
function dropRow(i) {
  const from = dragIdx.value
  dragIdx.value = overIdx.value = null
  if (from === null || from === i) return
  const arr = [...props.sorts]
  const [moved] = arr.splice(from, 1)
  arr.splice(i, 0, moved)
  emit('change', arr)
}
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.auto-sort { display: inline-flex; align-items: center; gap: 6px; }
.as-label { font-size: 13px; color: var(--st-text-2); }
.rule-row { display: flex; align-items: center; gap: 6px; border-top: 2px solid transparent; border-bottom: 2px solid transparent; }
.rule-row.drop-before { border-top-color: var(--st-primary); }
.rule-row.drop-after { border-bottom-color: var(--st-primary); }
.drag { color: var(--st-text-4); cursor: grab; display: inline-flex; }
.r-field { width: 140px; }
.r-del { cursor: pointer; color: var(--st-text-3); display: inline-flex; }
.r-del:hover { color: var(--st-primary); }
</style>
