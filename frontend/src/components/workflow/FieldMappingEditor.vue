<template>
  <div class="mapping-editor">
    <div v-for="(row, i) in rows" :key="i" class="map-row">
      <!-- 字段：输入框；表字段并进插入面板（字段赋值只认列名，不给变量分组） -->
      <el-input v-model="row.field" placeholder="字段名，或点右侧选择" size="small" class="f" @input="sync" />
      <VariablePicker v-if="fields.length" compact title="选择字段" :groups="fieldGroups"
        @insert="row.field = $event; sync()" />
      <el-input v-model="row.value" :ref="(el) => (inputRefs[i] = el)" placeholder="值或点右侧插入变量"
        size="small" class="v" @input="sync" />
      <VariablePicker :groups="vars" @insert="insertVar(i, $event)" />
      <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="rows.push({ field: undefined, value: '' })">+ 添加字段</el-button>
    <div v-if="!fields.length" class="hint">请先选择数据表</div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import VariablePicker from './VariablePicker.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  fields: { type: Array, default: () => [] },
  vars: { type: Array, default: () => [] },   // VariablePicker 的分组变量
})
const emit = defineEmits(['update:modelValue'])

// 字段选择的插入面板：只列表字段（插字段名）
const fieldGroups = computed(() =>
  props.fields.length
    ? [{ title: '表字段', items: props.fields.map((f) => ({ label: f.label, expr: f.field_name })) }]
    : []
)

const rows = ref([])
const inputRefs = ref([])

// 在光标处插入变量表达式（失焦后 selectionStart 仍保留），取不到光标就追加到末尾
function insertVar(i, expr) {
  const row = rows.value[i]
  if (!row) return
  const el = inputRefs.value[i]?.input || inputRefs.value[i]?.$el?.querySelector('input')
  const v = row.value || ''
  const start = el?.selectionStart ?? v.length
  row.value = v.slice(0, start) + expr + v.slice(el?.selectionEnd ?? start)
  sync()
  nextTick(() => {
    if (!el) return
    el.focus()
    el.selectionStart = el.selectionEnd = start + expr.length
  })
}

function fromObj(obj) {
  return Object.entries(obj || {}).map(([field, value]) => ({
    field,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}
rows.value = fromObj(props.modelValue)
watch(() => props.modelValue, (v) => {
  // 仅外部变化时重建（编辑过程中的回写与 rows 一致，跳过避免光标跳动）
  const cur = Object.fromEntries(rows.value.filter((r) => r.field).map((r) => [r.field, r.value]))
  if (JSON.stringify(cur) !== JSON.stringify(v || {})) rows.value = fromObj(v)
})

function sync() {
  const obj = {}
  for (const r of rows.value) {
    if (r.field) obj[r.field] = r.value
  }
  emit('update:modelValue', obj)
}
</script>

<style scoped>
.map-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.f { flex: 0 1 170px; min-width: 120px; }
.v { flex: 1; min-width: 100px; }
.hint { font-size: 12px; color: #909399; }
</style>
