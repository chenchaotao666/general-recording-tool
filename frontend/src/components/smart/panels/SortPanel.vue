<template>
  <!-- 排序面板（§5.3，对齐参照 docs/智慧表格/表格上方按钮/排序.png）：
       标题 + 自动排序开关 → 规则行（⋮⋮ 拖拽 + 字段下拉 + 方向两段切换 + ⊖）→「＋ 添加排序字段」。即时生效 -->
  <el-popover :hide-after="0" :visible="visible" placement="bottom-start" :width="500" popper-class="st-tbpanel">
    <template #reference><span class="sp-ref" @click="emit('update:visible', !visible)"><slot /></span></template>
    <div v-if="visible" class="sp">
      <div class="sp-head">
        <span class="tbp-title">排序</span>
        <span class="sp-auto">自动排序<el-switch :model-value="autoSort" @change="$emit('auto-sort', $event)" /></span>
      </div>
      <div v-for="(s, i) in draft" :key="s._k" v-reorder-feedback="dropClass(i)" class="sp-row" :class="dropClass(i)"
           @dragover.prevent="overIdx = i" @drop.prevent="dropRow(i)">
        <span class="tbp-drag st-icon-action" draggable="true" @dragstart="dragIdx = i" @dragend="dragIdx = overIdx = null"><StIcon name="drag" :size="15" /></span>
        <div class="sp-field">
          <TbFieldSelect :model-value="s.fieldId" :fields="fields" @update:model-value="(v) => update(i, { fieldId: v })" />
        </div>
        <DirToggle :model-value="s.direction" :labels="labelsOf(s)" @update:model-value="(v) => update(i, { direction: v })" />
        <span class="tbp-del st-icon-action" aria-label="删除" @click="remove(i)"><StIcon name="minus-circle" :size="20" /></span>
      </div>
      <button class="st-button tbp-add sp-add" :disabled="draft.length >= 5" @click="add"><StIcon name="plus" :size="15" />添加排序字段</button>
    </div>
  </el-popover>
</template>

<script setup>
import { vReorderFeedback } from '../../../smart/utils/reorderFeedback.js'
import { ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import TbFieldSelect from './TbFieldSelect.vue'
import DirToggle from './DirToggle.vue'
import { sortDirectionLabels } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  sorts: { type: Array, default: () => [] },
  autoSort: { type: Boolean, default: true },
})
const emit = defineEmits(['update:visible', 'change', 'auto-sort'])
// 由 SmartTablePage 外点判定关闭，body 上的字段选择浮层也属于面板交互。

// 本地草稿（保留尚未选字段的行）；每次变更只提交完整规则
let seq = 0
const draft = ref([])
watch(() => props.visible, (v) => { if (v) draft.value = props.sorts.map(s => ({ ...s, _k: ++seq })) }, { immediate: true })
function commit() { emit('change', draft.value.filter(s => s.fieldId).map(({ _k, ...s }) => s)) }

const labelsOf = (s) => sortDirectionLabels(props.fields.find(f => f.field_name === s.fieldId))
function update(i, patch) { draft.value = draft.value.map((s, j) => (j === i ? { ...s, ...patch } : s)); commit() }
function add() {
  const used = new Set(draft.value.map(s => s.fieldId))
  draft.value = [...draft.value, { fieldId: props.fields.find(f => !used.has(f.field_name))?.field_name || null, direction: 'asc', _k: ++seq }]
  commit()
}
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i); commit() }

// 拖拽：规则顺序即优先级
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
  const arr = [...draft.value]
  const [m] = arr.splice(from, 1)
  arr.splice(i, 0, m)
  draft.value = arr
  commit()
}
</script>

<style scoped>
.sp-ref { display: inline-flex; }
.sp { display: flex; flex-direction: column; gap: 6px; }
.sp-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.sp-auto { display: inline-flex; align-items: center; gap: 10px; font-size: var(--st-font-size); color: var(--st-text-2); }
.sp-row { display: flex; align-items: center; gap: 12px; border-top: 2px solid transparent; border-bottom: 2px solid transparent; }
.sp-field { flex: 1; min-width: 0; }
.sp-field :deep(.tbfs) { width: 100%; }
.sp-add { margin-left: 0; align-self: flex-start; }
</style>
