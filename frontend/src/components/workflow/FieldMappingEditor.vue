<template>
  <div class="mapping-editor">
    <div v-for="(row, i) in rows" :key="i" class="map-row">
      <el-select v-model="row.field" placeholder="字段" size="small" class="f" filterable @change="sync">
        <el-option v-for="f in fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
      </el-select>
      <el-input v-model="row.value" placeholder="值或 {模板}，如 {nodes.q.records.0.item}" size="small" class="v" @input="sync" />
      <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="rows.push({ field: undefined, value: '' })">+ 添加字段</el-button>
    <div v-if="!fields.length" class="hint">请先选择数据表</div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  fields: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const rows = ref([])

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
.f { width: 130px; }
.v { flex: 1; }
.hint { font-size: 12px; color: #909399; }
</style>
