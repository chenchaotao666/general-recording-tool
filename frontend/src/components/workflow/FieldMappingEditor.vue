<template>
  <div class="mapping-editor">
    <div v-for="(row, i) in rows" :key="i" class="map-row">
      <!-- 字段：有表字段时下拉选（必填字段带红星），allow-create 仍可手输；没有时退回输入框 + 选择面板 -->
      <el-select v-if="fields.length" v-model="row.field" size="small" class="f" filterable allow-create
        default-first-option placeholder="选择字段" @change="sync">
        <el-option v-for="f in fields" :key="f.field_name" :label="`${f.label}（${f.field_name}）`" :value="f.field_name">
          <span>{{ f.label }}（{{ f.field_name }}）</span>
          <span v-if="f.nullable === false" class="req">*</span>
        </el-option>
      </el-select>
      <el-input v-else v-model="row.field" placeholder="字段名" size="small" class="f" @input="sync" />
      <el-input v-model="row.value" :ref="(el) => (inputRefs[i] = el)" placeholder="值或点右侧插入变量"
        size="small" class="v" @input="sync" />
      <VariablePicker :groups="vars" @insert="insertVar(i, $event)" />
      <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="rows.push({ field: undefined, value: '' })">+ 添加字段</el-button>
    <div v-if="!fields.length" class="hint">请先选择数据表</div>
    <div v-else-if="prefilled" class="hint">已预填必填字段（标 *），只需填值；空值的行保存时会被忽略</div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import VariablePicker from './VariablePicker.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  fields: { type: Array, default: () => [] },
  vars: { type: Array, default: () => [] },   // VariablePicker 的分组变量
})
const emit = defineEmits(['update:modelValue'])

const rows = ref([])
const inputRefs = ref([])
const prefilled = ref(false)   // 已按表结构预填必填字段行（仅供提示文案显隐）

function fromObj(obj) {
  return Object.entries(obj || {}).map(([field, value]) => ({
    field,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}
// 先恢复已有映射，再注册预填 watch（immediate 同步执行）——否则缓存命中时预填的行会被 fromObj 覆盖
rows.value = fromObj(props.modelValue)

// 选表后预填必填字段行（标 *），用户只填值不用回忆字段名；已有映射/已有行时不打扰
watch(() => props.fields, (fs) => {
  if (!fs.length || rows.value.length) return
  const required = fs.filter((f) => f.nullable === false)
  if (required.length) {
    rows.value = required.map((f) => ({ field: f.field_name, value: '' }))
    prefilled.value = true
  }
}, { immediate: true })

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

watch(() => props.modelValue, (v) => {
  // 仅外部变化时重建（编辑过程中的回写与 rows 一致，跳过避免光标跳动）。
  // 注意：对比口径必须与 sync() 一致（跳过空值行），否则「选了字段还没填值」的行
  // 会因 sync 不落配置而永远比对不等，被误判为外部变化重建掉（行突然消失）
  const cur = {}
  for (const r of rows.value) if (r.field && r.value !== '') cur[r.field] = r.value
  if (JSON.stringify(cur) !== JSON.stringify(v || {})) rows.value = fromObj(v)
})

function sync() {
  const obj = {}
  for (const r of rows.value) {
    // 空值行（含预填后未填的必填行）不落配置：字段赋值语义是「要写入什么」，空串只会写脏数据
    if (r.field && r.value !== '') obj[r.field] = r.value
  }
  emit('update:modelValue', obj)
}
</script>

<style scoped>
.map-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.f { flex: 0 1 170px; min-width: 120px; }
.v { flex: 1; min-width: 100px; }
.hint { font-size: 12px; color: #909399; }
.req { color: #f56c6c; margin-left: 4px; }
</style>
