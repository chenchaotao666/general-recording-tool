<template>
  <div class="cases-editor">
    <div v-for="(c, i) in rows" :key="i" class="case-row">
      <el-input v-model="c.label" size="small" class="lb" placeholder="分支名，如 紧急" @input="sync" />
      <!-- 字段支持键名或完整变量表达式（引擎兼容两种形态），显示与其它输入框一致 -->
      <el-input v-model="c.field" size="small" class="f" placeholder="字段名，或点右侧选择" @input="sync" />
      <VariablePicker compact title="选择字段或变量" :groups="fieldGroups" @insert="insertField(i, $event)" />
      <el-select v-model="c.op" size="small" class="op" @change="sync">
        <el-option v-for="[v, l] in OPS" :key="v" :label="l" :value="v" />
      </el-select>
      <el-input v-if="!NO_VALUE_OPS.includes(c.op)" v-model="c.value" placeholder="值或 {模板}" size="small" class="v"
        :ref="(el) => (valRefs[i] = el)" @focus="focused[i] = true" @input="sync" />
      <VariablePicker v-if="vars.length && !NO_VALUE_OPS.includes(c.op)" compact title="插入变量到值" :groups="vars"
        @insert="insertVal(i, $event)" />
      <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="add">+ 添加分支</el-button>
    <div class="hint">从上到下第一个命中的分支生效；都不命中走「默认」分支。字段可填键名（如 urgency）或点 ⚡ 选变量（如 {nodes.llm_1.data.urgency}）</div>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import VariablePicker from './VariablePicker.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },   // [{label, field, op, value}]
  fields: { type: Array, default: () => [] },
  vars: { type: Array, default: () => [] },         // 变量分组（上游输出 + 触发器 + 内置时间变量）
})
const emit = defineEmits(['update:modelValue'])

// 字段选择并进插入面板：有关联表字段时列「表字段」分组（插字段名），后面跟变量分组（插 {表达式}）
const fieldGroups = computed(() => {
  const groups = []
  if (props.fields.length) {
    groups.push({ title: '表字段', items: props.fields.map((f) => ({ label: f.label, expr: f.field_name })) })
  }
  return [...groups, ...props.vars]
})

// 选中变量后保留完整表达式（引擎兼容键名和表达式两种形态），显示与其它输入框一致
function insertField(i, expr) {
  const c = rows.value[i]
  if (!c) return
  c.field = expr
  sync()
}

// 在光标处插入变量：输入框聚焦过 → 按光标位置插；从未聚焦 → 整体替换（分支值是标量）
const valRefs = reactive({})
const focused = reactive({})
function insertVal(i, expr) {
  const c = rows.value[i]
  if (!c) return
  const v = c.value === undefined || c.value === null ? '' : String(c.value)
  const el = valRefs[i]?.input || valRefs[i]?.$el?.querySelector('input')
  if (el && focused[i]) {
    const start = el.selectionStart ?? v.length
    c.value = v.slice(0, start) + expr + v.slice(el.selectionEnd ?? start)
    nextTick(() => {
      el.focus()
      el.selectionStart = el.selectionEnd = start + expr.length
    })
  } else {
    c.value = expr
  }
  sync()
}

const NO_VALUE_OPS = ['null', 'not_null', 'today']
const OPS = [
  ['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'],
  ['contains', '包含'], ['startswith', '开头是'], ['in', '属于（多选）'],
  ['null', '为空'], ['not_null', '不为空'],
]

const rows = ref((props.modelValue || []).map((c) => ({ ...c })))
watch(() => props.modelValue, (v) => {
  if (JSON.stringify(rows.value) !== JSON.stringify(v || [])) {
    rows.value = (v || []).map((c) => ({ ...c }))
  }
})

function add() {
  rows.value.push({ label: '', field: undefined, op: 'eq', value: undefined })
  sync()
}
function sync() {
  emit('update:modelValue', rows.value.map((c) => ({ ...c })))
}
</script>

<style scoped>
.case-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.lb { flex: 0 1 90px; min-width: 76px; }
.f { flex: 1 1 100px; min-width: 90px; }
.op { width: 96px; flex-shrink: 0; }
.v { flex: 1 1 80px; min-width: 70px; }
.hint { font-size: 12px; color: #909399; margin-top: 2px; }
</style>
