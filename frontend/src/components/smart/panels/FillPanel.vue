<template>
  <!-- 填色面板（§5.5）：规则行 = 字段 + 运算符 + 值 → 颜色；条件不完整不生效不计数。
       草稿模式：面板内自由编辑，点「确定」才落库 -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="460">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head"><b>填色</b></div>
      <div v-for="(r, i) in draft" :key="r.id || i" class="rule-row">
        <el-select :teleported="false" :model-value="r.fieldId" size="small" class="r-field" placeholder="字段"
                   @change="(v) => update(i, { fieldId: v, fillTarget: null, operator: defaultOp(v), value: undefined })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <!-- 填色目标统一下拉（设计稿 PixPin_2026-10-16_00-26-12）：
             所有内容 / 字段名称 + 「筛选」分组运算符；选中运算符且需要取值时出现值编辑器 -->
        <el-select :teleported="false" :model-value="targetOf(r)" size="small"
                   :class="needsValue(r) ? 'r-op' : 'r-target'" placeholder="条件"
                   @change="(v) => onTargetChange(i, v)">
          <el-option value="__all" label="所有内容" />
          <el-option value="__header" label="字段名称" />
          <el-option-group v-if="opsOf(r).length" label="筛选">
            <el-option v-for="op in opsOf(r)" :key="op" :value="op" :label="OP_LABELS[op]" />
          </el-option-group>
        </el-select>
        <ConditionValue v-if="needsValue(r)" :field="fieldOf(r)"
                        :operator="r.operator" :value="r.value" @update="(v) => update(i, { value: v })" />
        <span class="arrow">→</span>
        <!-- 颜色设置（设计稿 PixPin_2026-10-15_20-24-52 / 20-26-47）：色块 + ▾，
             弹出 9 色 × 3 深浅档预设色板 + 整行填色勾选 -->
        <div class="r-color" @click.stop="togglePalette(i)">
          <span class="rc-swatch" :style="{ background: r.color || 'transparent' }" />
          <span class="rc-caret">▾</span>
          <div v-if="paletteIdx === i" class="rc-pop" @click.stop @mousedown.stop>
            <div v-for="(row, ri) in FILL_PALETTE" :key="ri" class="rc-row">
              <span v-for="c in row" :key="c" class="rc-cell" :class="{ on: r.color === c }"
                    :style="{ background: c }" @click="pickColor(i, c)" />
            </div>
            <el-checkbox size="small" :model-value="!!r.wholeRow"
                         @change="(v) => update(i, { wholeRow: v })">整行填色</el-checkbox>
          </div>
        </div>
        <span class="r-del" @click.stop="remove(i)">⊖</span>
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
import { filterOpsOf, OP_LABELS, NO_VALUE_OPS, FILL_PALETTE } from '../../../smart/registry/fieldRegistry.js'

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
function defaultOp(fieldName) {
  const f = props.fields.find(x => x.field_name === fieldName)
  return f ? filterOpsOf(f)[0] : null
}
// 统一下拉（所有内容/字段名称/运算符）的取值与切换
const targetOf = (r) => (r.fillTarget ? `__${r.fillTarget}` : (opsOf(r).includes(r.operator) ? r.operator : null))
const needsValue = (r) => !r.fillTarget && r.operator && !NO_VALUE_OPS.includes(r.operator)
function onTargetChange(i, v) {
  if (v === '__all' || v === '__header') update(i, { fillTarget: v.slice(2), operator: null, value: undefined })
  else update(i, { fillTarget: null, operator: v, value: undefined })
}
function update(i, patch) { draft.value = draft.value.map((r, j) => (j === i ? { ...r, ...patch } : r)) }
function add() {
  draft.value = [...draft.value, { id: `f_${Date.now()}`, fieldId: null, operator: null, value: undefined, color: '#fef9e0', wholeRow: false, order: draft.value.length }]
}
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i) }

// 色板弹层：单例（同时只开一行的色板），外点关闭
const paletteIdx = ref(null)
function togglePalette(i) { paletteIdx.value = paletteIdx.value === i ? null : i }
function pickColor(i, c) { update(i, { color: c }); paletteIdx.value = null }
watch(paletteIdx, (v) => {
  if (v == null) return
  const close = (e) => {
    if (e.target.closest?.('.rc-pop')) return
    paletteIdx.value = null
    document.removeEventListener('mousedown', close)
  }
  setTimeout(() => document.addEventListener('mousedown', close), 0)
})
watch(() => props.visible, (v) => { if (!v) paletteIdx.value = null })

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
.r-target { flex: 1; }   /* 整列规则的目标选择占满运算符+取值区 */
.arrow { color: var(--el-text-color-placeholder); }
.r-del { cursor: pointer; color: var(--el-color-danger); }
/* 颜色设置：色块按钮（色块 + ▾）与预设色板弹层 */
.r-color {
  display: flex; align-items: center; gap: 4px; position: relative; cursor: pointer;
  border: 1px solid var(--el-border-color); border-radius: 4px; padding: 4px 6px;
}
.r-color:hover { border-color: var(--el-color-primary); }
.rc-swatch { width: 30px; height: 16px; border-radius: 2px; border: 1px solid var(--el-border-color-lighter); }
.rc-caret { font-size: 10px; color: var(--el-text-color-placeholder); }
.rc-pop {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 10;
  background: #fff; border-radius: 8px; box-shadow: var(--el-box-shadow);
  padding: 10px; display: flex; flex-direction: column; gap: 8px;
}
.rc-row { display: flex; gap: 6px; }
.rc-cell { width: 22px; height: 22px; border-radius: 4px; cursor: pointer; box-sizing: border-box; }
.rc-cell:hover { transform: scale(1.1); }
.rc-cell.on { outline: 2px solid var(--el-color-primary); outline-offset: 1px; }
</style>
