<template>
  <div class="filters-editor">
    <div class="logic-row" v-if="model.rules.length > 0">
      <span>满足</span>
      <el-radio-group :model-value="model.logic" size="small" @update:model-value="setLogic">
        <el-radio-button value="AND">全部条件</el-radio-button>
        <el-radio-button value="OR">任一条件</el-radio-button>
      </el-radio-group>
      <span v-if="model.rules.length < 2" class="unit">（加两条以上条件时生效）</span>
    </div>
    <div v-for="(r, i) in model.rules" :key="i" class="rule-row">
      <!-- 字段：输入框；选项并进「插入变量」面板（表字段插字段名，上游/内置变量插 {表达式}） -->
      <el-input v-model="r.field" placeholder="字段名，或点右侧选择" size="small" class="f" />
      <VariablePicker compact title="选择字段或变量" :groups="fieldGroups" @insert="insertField(i, $event)" />
      <el-select v-model="r.op" size="small" class="op">
        <el-option v-for="[v, l] in opsFor(r.field)" :key="v" :label="l" :value="v" />
      </el-select>
      <template v-if="!NO_VALUE_OPS.includes(r.op)">
        <!-- 从插入面板点了「日期选择/日期时间选择」：值控件换成对应选择器（优先于模板值——用户明确选了日期）。
             用 update:model-value 而不是 @change（面板点选/清空都会触发）。控件类型有粘性：清空不改类型 -->
        <el-date-picker v-if="ctlMode[i]" :key="`ctl-${i}-${ctlMode[i]}`" :model-value="r.value"
          :type="ctlMode[i]" :value-format="ctlMode[i] === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss'"
          size="small" class="v" @update:model-value="onDatePicked(i, $event)" />
        <!-- 值是模板字符串（如 {trigger.record.id}）时只能用文本框，数字/日期框会显示成空。
             文本框里输入过（含清空模板）的行标记 textMode，不再自动掉回日期选择器 -->
        <el-input v-else-if="isTpl(r.value)" v-model="r.value" placeholder="{模板变量}" size="small" class="v"
          :ref="(el) => (valRefs[i] = el)" @focus="focused[i] = true" @input="textMode[i] = true" />
        <el-input-number v-else-if="DAY_OPS.includes(r.op)" v-model="r.value" :min="0" size="small" controls-position="right" class="v" />
        <el-input-number v-else-if="isNumber(r.field)" v-model="r.value" size="small" controls-position="right" class="v" />
        <!-- 日期值：datetime 字段（或值里已带时间/选过日期时间）用 datetime 选择器，否则纯日期；
             文本模式（输入过模板/文本）的行保持文本框；
             :key 强制重建，避免 type 切换时面板状态错乱 -->
        <el-date-picker v-else-if="isDate(r.field) && !textMode[i]" :key="`dp-${i}-${withTime(r, i)}`" :model-value="r.value"
          :type="withTime(r, i) ? 'datetime' : 'date'"
          :value-format="withTime(r, i) ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD'" size="small" class="v"
          @update:model-value="onDatePicked(i, $event)" />
        <el-input v-else v-model="r.value" placeholder="值" size="small" class="v"
          :ref="(el) => (valRefs[i] = el)" @focus="focused[i] = true" @input="textMode[i] = true" />
      </template>
      <VariablePicker v-if="vars.length && !NO_VALUE_OPS.includes(r.op)" compact title="插入变量到值" :groups="vars"
        control-pick @insert="insertVal(i, $event)" @pick-control="setCtl(i, $event)" />
      <span v-if="DAY_OPS.includes(r.op)" class="unit">天</span>
      <el-button link type="danger" size="small" @click="model.rules.splice(i, 1)">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="add">+ 添加条件</el-button>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive } from 'vue'
import VariablePicker from './VariablePicker.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ logic: 'AND', rules: [] }) },
  fields: { type: Array, default: () => [] },   // MetaField 列表；字段名也可手填（LLM JSON 键等场景）
  vars: { type: Array, default: () => [] },     // 可插入的变量分组（上游输出 + 内置时间变量）
})
const emit = defineEmits(['update:modelValue'])

// 字段选择并进插入面板：有表字段时列「表字段」分组（插字段名），后面跟变量分组（插 {表达式}）
const fieldGroups = computed(() => {
  const groups = []
  if (props.fields.length) {
    groups.push({
      title: '表字段',
      items: [
        ...props.fields.map((f) => ({ label: f.label, expr: f.field_name })),
        { label: 'ID', expr: 'id' },
        { label: '创建时间', expr: 'created_at' },
        { label: '更新时间', expr: 'updated_at' },
      ],
    })
  }
  return [...groups, ...props.vars]
})

// 选中后原样填入（字段名或完整变量表达式，引擎两种形态都兼容），显示与其它输入框一致
function insertField(i, expr) {
  const r = model.value.rules[i]
  if (r) r.field = expr
}

// 值是模板字符串（含 { }）时切文本框——数字/日期控件会把模板值显示成空白
const isTpl = (v) => typeof v === 'string' && v.includes('{')

// 从插入面板点了「日期选择/日期时间选择」后，该行的值控件换成对应选择器（行号 → date/datetime）
// 注意必须用 reactive 而不是 ref({})：模板里 ctlMode[i] 的成员读写不会对 ref 做 .value 解包，ref 会静默失效
const ctlMode = reactive({})
// 在文本框里输入过内容的行保持文本框（清空模板不再自动掉回日期选择器）
const textMode = reactive({})
// 值控件是「日期时间」的粘性标记：清空内容不降级成纯日期（控件类型不随值清空而变化）
const timeMode = reactive({})

function setCtl(i, mode) {
  ctlMode[i] = mode
  if (mode === 'datetime') timeMode[i] = true
}

// 日期控件选值/清空统一入口。清空：控件类型保持不动（带时间的值清空后仍是日期时间控件）；选完：退出覆盖态
function onDatePicked(i, v) {
  const r = model.value.rules[i]
  if (!r) return
  const hadTime = typeof r.value === 'string' && /\s\d{1,2}:\d{2}/.test(r.value)
  r.value = v
  if (v === null || v === undefined || v === '') {
    if (hadTime) timeMode[i] = true   // 清空了带时间的值 → 控件保持日期时间形态
    return
  }
  delete ctlMode[i]
  delete textMode[i]
  if (typeof v === 'string' && /\s\d{1,2}:\d{2}/.test(v)) timeMode[i] = true
  else delete timeMode[i]
}

// 在光标处插入变量：输入框聚焦过 → 按光标位置插；从未聚焦 → 整体替换（筛选值是标量，语义更合理）
const valRefs = reactive({})
const focused = reactive({})
function insertVal(i, expr) {
  const r = model.value.rules[i]
  if (!r) return
  delete ctlMode[i]   // 插入了变量 → 值回到文本框（日期选择器的覆盖态失效）
  const v = r.value === undefined || r.value === null ? '' : String(r.value)
  const el = valRefs[i]?.input || valRefs[i]?.$el?.querySelector('input')
  if (el && focused[i]) {
    const start = el.selectionStart ?? v.length
    r.value = v.slice(0, start) + expr + v.slice(el.selectionEnd ?? start)
    nextTick(() => {
      el.focus()
      el.selectionStart = el.selectionEnd = start + expr.length
    })
  } else {
    r.value = expr
  }
}

const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']
const OPS = {
  text: [['eq', '等于'], ['ne', '不等于'], ['contains', '包含'], ['startswith', '开头是'], ['null', '为空'], ['not_null', '不为空']],
  number: [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'], ['null', '为空'], ['not_null', '不为空']],
  date: [['eq', '等于'], ['gte', '不早于'], ['lte', '不晚于'], ['today', '当天'], ['past_days', '过去 N 天'], ['older_than_days', '早于 N 天前'], ['within_days', '未来 N 天内'], ['null', '为空'], ['not_null', '不为空']],
  bool: [['eq', '等于'], ['null', '为空'], ['not_null', '不为空']],
  select: [['eq', '等于'], ['ne', '不等于'], ['in', '属于（多选）'], ['null', '为空'], ['not_null', '不为空']],
}
// 未知字段（AI 生成/历史配置）兜底：给全量操作符，保证中文 label 都能显示
const ALL_OPS = [...new Map([...OPS.text, ...OPS.number, ...OPS.date, ...OPS.bool, ...OPS.select]
  .map(([v, l]) => [v, [v, l]])).values()]

const model = computed({
  get: () => props.modelValue || { logic: 'AND', rules: [] },
  set: (v) => emit('update:modelValue', v),
})

function setLogic(v) { emit('update:modelValue', { ...model.value, logic: v }) }
function add() {
  const rules = [...model.value.rules, { field: undefined, op: 'eq', value: undefined }]
  emit('update:modelValue', { ...model.value, rules })
}
function fieldOf(name) {
  if (name === 'created_at' || name === 'updated_at') return { data_type: 'datetime', widget: 'datetime-picker' }
  if (name === 'id') return { data_type: 'int', widget: 'number' }
  return props.fields.find((f) => f.field_name === name)
}
function opsFor(name) {
  const f = fieldOf(name)
  if (!f) return ALL_OPS
  if (f.widget === 'select') return OPS.select
  if (['int', 'decimal'].includes(f.data_type)) return OPS.number
  if (['date', 'datetime'].includes(f.data_type)) return OPS.date
  if (f.data_type === 'bool') return OPS.bool
  return OPS.text
}
const isNumber = (n) => ['int', 'decimal'].includes(fieldOf(n)?.data_type)
const isDate = (n) => ['date', 'datetime'].includes(fieldOf(n)?.data_type)
// 日期值控件带不带时间：datetime 字段固定带；date 字段看值里有没有时间（如插入了 2026-09-27 14:30:00）
// 或该行通过「日期时间选择」选过（timeMode 粘性——清空内容不降级）
const withTime = (r, i) =>
  fieldOf(r.field)?.data_type === 'datetime' || !!timeMode[i]
  || (typeof r.value === 'string' && /\s\d{1,2}:\d{2}/.test(r.value))
</script>

<style scoped>
.logic-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px; color: #909399; }
.rule-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.f { flex: 1 1 140px; min-width: 120px; }
.op { width: 110px; flex-shrink: 0; }
.v { flex: 1 1 100px; min-width: 90px; }
.unit { font-size: 12px; color: #909399; }
</style>
