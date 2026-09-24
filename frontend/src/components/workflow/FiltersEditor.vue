<template>
  <div class="filters-editor">
    <div class="logic-row" v-if="model.rules.length > 1">
      <span>满足</span>
      <el-radio-group :model-value="model.logic" size="small" @update:model-value="setLogic">
        <el-radio-button value="AND">全部条件</el-radio-button>
        <el-radio-button value="OR">任一条件</el-radio-button>
      </el-radio-group>
    </div>
    <div v-for="(r, i) in model.rules" :key="i" class="rule-row">
      <el-select v-model="r.field" placeholder="字段" size="small" class="f" filterable
        :allow-create="!fields.length" @change="r.value = undefined">
        <el-option v-for="f in fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
        <el-option label="ID" value="id" />
        <el-option label="创建时间" value="created_at" />
        <el-option label="更新时间" value="updated_at" />
        <!-- 兜底：AI 生成/历史配置里的字段名不在当前字段清单时，原样显示不丢值 -->
        <el-option v-if="r.field && !knownFields.has(r.field)" :label="`${r.field}（未知字段）`" :value="r.field" />
      </el-select>
      <el-select v-model="r.op" size="small" class="op">
        <el-option v-for="[v, l] in opsFor(r.field)" :key="v" :label="l" :value="v" />
      </el-select>
      <template v-if="!NO_VALUE_OPS.includes(r.op)">
        <el-input-number v-if="DAY_OPS.includes(r.op)" v-model="r.value" :min="0" size="small" controls-position="right" class="v" />
        <el-input-number v-else-if="isNumber(r.field)" v-model="r.value" size="small" controls-position="right" class="v" />
        <el-date-picker v-else-if="isDate(r.field)" v-model="r.value" type="date" value-format="YYYY-MM-DD" size="small" class="v" />
        <el-input v-else v-model="r.value" placeholder="值" size="small" class="v" />
      </template>
      <span v-if="DAY_OPS.includes(r.op)" class="unit">天</span>
      <el-button link type="danger" size="small" @click="model.rules.splice(i, 1)">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="add">+ 添加条件</el-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ logic: 'AND', rules: [] }) },
  fields: { type: Array, default: () => [] },   // MetaField 列表；空时字段名手填
})
const emit = defineEmits(['update:modelValue'])

const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']
const OPS = {
  text: [['eq', '等于'], ['ne', '不等于'], ['contains', '包含'], ['startswith', '开头是'], ['null', '为空'], ['not_null', '不为空']],
  number: [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'], ['null', '为空'], ['not_null', '不为空']],
  date: [['eq', '等于'], ['gte', '不早于'], ['lte', '不晚于'], ['today', '当天'], ['past_days', '过去 N 天'], ['older_than_days', '早于 N 天前'], ['within_days', '未来 N 天内'], ['null', '为空'], ['not_null', '不为空']],
  bool: [['eq', '等于'], ['null', '为空'], ['not_null', '不为空']],
  select: [['eq', '等于'], ['ne', '不等于'], ['in', '属于（多选）'], ['null', '为空'], ['not_null', '不为空']],
}

const model = computed({
  get: () => props.modelValue || { logic: 'AND', rules: [] },
  set: (v) => emit('update:modelValue', v),
})

// 已知字段集合（业务字段 + 系统字段），用于给未知字段名做兜底选项
const knownFields = computed(() =>
  new Set([...props.fields.map((f) => f.field_name), 'id', 'created_at', 'updated_at'])
)

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
  if (!f) return OPS.text
  if (f.widget === 'select') return OPS.select
  if (['int', 'decimal'].includes(f.data_type)) return OPS.number
  if (['date', 'datetime'].includes(f.data_type)) return OPS.date
  if (f.data_type === 'bool') return OPS.bool
  return OPS.text
}
const isNumber = (n) => ['int', 'decimal'].includes(fieldOf(n)?.data_type)
const isDate = (n) => ['date', 'datetime'].includes(fieldOf(n)?.data_type)
</script>

<style scoped>
.logic-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px; color: #909399; }
.rule-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.f { width: 130px; }
.op { width: 110px; }
.v { flex: 1; min-width: 90px; }
.unit { font-size: 12px; color: #909399; }
</style>
