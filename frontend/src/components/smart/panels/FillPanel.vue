<template>
  <!-- 填色面板（§5.5，对齐参照 docs/智慧表格/表格上方按钮/填色.png）：
       规则行 = ⋮⋮ + 字段 + 目标/条件（字段名称 / 所有内容 / 筛选运算符）+ [值] → 色块 ▾ + ⊖；
       色板：9 色 × 3 深浅 + 整行填色。条件不完整不生效不计数；即时生效 -->
  <el-popover :hide-after="0" :visible="visible" placement="bottom-start" :width="760"
              :popper-options="FIXED_POPPER" :popper-style="{ maxWidth: 'calc(100vw - 24px)', boxSizing: 'border-box' }" popper-class="st-tbpanel">
    <template #reference><span class="flp-ref" @click="emit('update:visible', !visible)"><slot /></span></template>
    <div v-if="visible" class="flp">
      <div class="flp-head"><span class="tbp-title">填色</span></div>
      <div class="flp-scroll">
      <div v-for="(r, i) in draft" :key="r.id" v-reorder-feedback="dropClass(i)" class="flp-row" :class="dropClass(i)"
           @dragover.prevent="overIdx = i" @drop.prevent="dropRow(i)">
        <span class="tbp-drag st-icon-action" draggable="true" @dragstart="dragIdx = i" @dragend="dragIdx = overIdx = null"><StIcon name="drag" :size="15" /></span>
        <TbFieldSelect :model-value="r.fieldId" :fields="fields" placeholder="字段" class="flp-field"
                       @update:model-value="(v) => update(i, { fieldId: v, fillTarget: 'all', operator: null, value: undefined })" />
        <el-select class="st-control" :teleported="true" :popper-options="FIXED_POPPER" :model-value="targetOf(r)" :class="needsValue(r) ? 'flp-op' : 'flp-target'" placeholder="条件"
                   @change="(v) => onTargetChange(i, v)">
          <el-option value="__header" label="字段名称" />
          <el-option value="__all" label="所有内容" />
          <el-option-group v-if="opsOf(r).length" label="满足条件时">
            <el-option v-for="op in opsOf(r)" :key="op" :value="op" :label="opLabel(fieldOf(r), op)" />
          </el-option-group>
        </el-select>
        <div v-if="needsValue(r)" class="flp-val">
          <ConditionValue :field="fieldOf(r)" :operator="r.operator" :value="r.value" @update="(v) => update(i, { value: v })" />
        </div>
        <span class="flp-arrow">→</span>
        <el-popover :visible="paletteIdx === i" @update:visible="v => { if (v) paletteIdx = i; else if (paletteIdx === i) paletteIdx = null }"
                    trigger="click" :hide-after="0" placement="bottom-end" :width="320" :teleported="true" :show-arrow="false"
                    :popper-options="FIXED_POPPER" :popper-style="{ padding: '18px 20px 14px', maxWidth: 'calc(100vw - 24px)', boxSizing: 'border-box' }"
                    popper-class="fill-palette-pop">
          <template #reference>
          <div class="st-control st-control--native flp-color" :class="{ open: paletteIdx === i }">
            <span class="flp-swatch" :style="{ background: r.color || '#fff' }" />
            <SmartSelectArrow :open="paletteIdx === i" />
          </div>
          </template>
          <div class="flp-pal" @click.stop @mousedown.stop>
            <div v-for="(row, ri) in FILL_PALETTE" :key="ri" class="flp-pal-row">
              <span v-for="c in row" :key="c" class="flp-cell" :class="{ on: r.color === c }" :style="{ background: c }" @click="pickColor(i, c)" />
            </div>
            <label class="flp-whole"><el-checkbox :model-value="!!r.wholeRow" @change="(v) => update(i, { wholeRow: v })" />整行填色</label>
          </div>
        </el-popover>
        <span class="tbp-del st-icon-action" aria-label="删除" @click="remove(i)"><StIcon name="minus-circle" :size="20" /></span>
      </div>
      </div>
      <button class="st-button tbp-add flp-add" @click="add"><StIcon name="plus" :size="15" />添加条件</button>
    </div>
  </el-popover>
</template>

<script setup>
import { vReorderFeedback } from '../../../smart/utils/reorderFeedback.js'
import { ref, watch } from 'vue'
import ConditionValue from './ConditionValue.vue'
import TbFieldSelect from './TbFieldSelect.vue'
import StIcon from '../icons/StIcon.vue'
import SmartSelectArrow from '../common/SmartSelectArrow.vue'
import { filterOpsOf, opLabel, NO_VALUE_OPS, FILL_PALETTE } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  rules: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'change'])
// 外层仅受 props 控制，外点关闭复用 SmartTablePage 对 .el-popper 的判定。
const FIXED_POPPER = { strategy: 'fixed', modifiers: [
  { name: 'preventOverflow', options: { boundary: [], rootBoundary: 'viewport', padding: 12, altAxis: true, tether: false } },
] }

const draft = ref([])
const paletteIdx = ref(null)   // 色板：同一时间只开一行
watch(() => props.visible, (v) => {
  if (v) draft.value = props.rules.map((r) => ({ ...r, id: r.id || `f_${Math.random().toString(36).slice(2, 8)}` }))
  else paletteIdx.value = null
}, { immediate: true })

const fieldOf = (r) => props.fields.find(f => f.field_name === r.fieldId)
const opsOf = (r) => (fieldOf(r) ? filterOpsOf(fieldOf(r)) : [])
const targetOf = (r) => (r.fillTarget ? `__${r.fillTarget}` : (opsOf(r).includes(r.operator) ? r.operator : null))
const needsValue = (r) => !r.fillTarget && r.operator && !NO_VALUE_OPS.includes(r.operator)

// 即时生效：只提交选了字段的规则（是否完整由渲染层判定生效）
let timer = null
function commit() {
  clearTimeout(timer)
  timer = setTimeout(() => emit('change', draft.value.filter(r => r.fieldId).map((r, k) => ({ ...r, order: k }))), 250)
}
function update(i, patch) { draft.value = draft.value.map((r, j) => (j === i ? { ...r, ...patch } : r)); commit() }
function onTargetChange(i, v) {
  if (v === '__all' || v === '__header') update(i, { fillTarget: v.slice(2), operator: null, value: undefined })
  else update(i, { fillTarget: null, operator: v, value: undefined })
}
function add() {
  draft.value = [...draft.value, { id: `f_${Date.now()}`, fieldId: null, fillTarget: 'all', operator: null, value: undefined,
                                   color: FILL_PALETTE[0][5], wholeRow: false }]
}
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i); commit() }

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

// 选择颜色后保持色板打开，可继续勾选整行填色；外点关闭由 ElPopover 处理。
function pickColor(i, c) { update(i, { color: c }) }
</script>

<style scoped>
.flp-ref { display: inline-flex; }
.flp { display: flex; flex-direction: column; gap: 6px; min-width: 0; max-height: calc(100dvh - 64px); overflow: hidden; }
.flp-head, .flp-add { flex-shrink: 0; }
.flp-scroll { display: flex; flex-direction: column; gap: 6px; min-height: 0; overflow: auto; }
.flp-scroll > .flp-row { flex-shrink: 0; }
.flp-head { margin-bottom: 6px; }
.flp-row { display: flex; align-items: center; gap: 10px; border-top: 2px solid transparent; border-bottom: 2px solid transparent; }
.flp-row :deep(.flp-field) { width: 180px; flex: none; }
.flp-target { flex: 1; min-width: 0; }
.flp-op { width: 112px; flex: none; }
/* 值列吃掉剩余宽度；里面的编辑器（日期/数字/标签选择）一律撑满本列、不得溢出盖住「→」和色块 */
.flp-val { flex: 1; min-width: 0; display: flex; align-items: center; }
.flp-val > * { flex: 1; min-width: 0; }
.flp-val :deep(.el-date-editor.el-input) { height: 36px; }
.flp-val :deep(.el-date-editor .el-input__wrapper) { height: 100%; box-sizing: border-box; }
.flp-val :deep(.el-date-editor.el-input), .flp-val :deep(.el-date-editor),
.flp-val :deep(.el-input-number), .flp-val :deep(.val-editor), .flp-val :deep(.el-input) { width: 100% !important; min-width: 0; }
.flp-val :deep(.enum-val) { width: 100%; box-sizing: border-box; }
.flp-target :deep(.el-select__wrapper), .flp-op :deep(.el-select__wrapper) { min-height: 36px; border-radius: 6px; font-size: var(--st-font-size); }
.flp-val :deep(.el-input__wrapper), .flp-val :deep(.el-select__wrapper) { min-height: 36px; }
.flp-val :deep(.enum-val) { min-height: 36px; }
.flp-arrow { color: var(--st-text-2); flex: none; font-size: var(--st-font-size); }
.flp-color { position: relative; display: inline-flex; align-items: center; gap: 8px; height: 36px; box-sizing: border-box; padding: 0 10px 0 5px;
             border: 1px solid var(--st-border); border-radius: 6px; cursor: pointer; flex: none; background: #fff; }
.flp-color:hover, .flp-color.open { border-color: #C9CCD1; }
.flp-swatch { width: 64px; height: 20px; border-radius: 3px; }
.flp-caret { color: var(--st-text-3); }
.flp-pal { max-height: calc(100dvh - 60px); overflow: auto; cursor: default; }
.flp-pal-row { display: grid; grid-template-columns: repeat(9, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.flp-cell { aspect-ratio: 1; border-radius: 3px; cursor: pointer; box-sizing: border-box; }
.flp-cell.on { box-shadow: 0 0 0 1px #fff inset, 0 0 0 2px var(--st-primary); }
.flp-cell:hover { transform: scale(1.08); }
.flp-whole { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.flp-add { margin-left: 0; align-self: flex-start; }
@media (max-width: 720px) {
  .flp-row { flex-wrap: wrap; padding: 6px 0; gap: 8px; }
  .flp-row :deep(.flp-field) { width: calc(100% - 32px); min-width: 0; }
  .flp-op, .flp-target { flex: 1 1 120px; width: auto; }
  .flp-val { flex: 1 1 160px; }
  .flp-swatch { width: 40px; }
}
</style>
