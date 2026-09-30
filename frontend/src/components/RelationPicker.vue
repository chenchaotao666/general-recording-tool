<template>
  <el-select
    :model-value="modelValue" filterable remote clearable :remote-method="search"
    :loading="loading" :placeholder="placeholder" style="width: 100%"
    @update:model-value="onChange" @focus="ensureInit"
  >
    <el-option
      v-for="opt in options" :key="String(opt.value)" :label="opt.label" :value="opt.value"
    />
  </el-select>
</template>

<script setup>
import { ref } from 'vue'
import { listRecords } from '../api'

// 关联选择器：从目标表远程搜索记录；选中后 emit carry 事件（携带整行，供 carry_fields 回填）
const props = defineProps({
  modelValue: { default: null },
  relation: { type: Object, required: true },   // {table_id, value_field, label_field, carry_fields?}
  placeholder: { type: String, default: '请选择' },
})
const emit = defineEmits(['update:modelValue', 'carry'])

const options = ref([])
const loading = ref(false)
const inited = ref(false)
const rowCache = new Map()   // value → 整行记录（供 carry 回填与标签回显）

function toOpt(row) {
  const value = row[props.relation.value_field]
  const label = row[props.relation.label_field]
  return {
    value,
    label: props.relation.value_field === props.relation.label_field
      ? String(label ?? value ?? '')
      : `${label ?? ''}（${value ?? ''}）`,
  }
}

async function fetchRows(keyword, exactValue) {
  loading.value = true
  try {
    const filters = []
    if (exactValue !== undefined && exactValue !== null && exactValue !== '') {
      filters.push({ field: props.relation.value_field, op: 'eq', value: exactValue })
    } else if (keyword) {
      filters.push({ field: props.relation.label_field, op: 'contains', value: keyword })
    }
    const res = await listRecords(props.relation.table_id, {
      page: 1, page_size: 20,
      filters: JSON.stringify(filters),
    })
    for (const row of res.items) rowCache.set(row[props.relation.value_field], row)
    return res.items.map(toOpt)
  } catch {
    return []
  } finally {
    loading.value = false
  }
}

async function search(keyword) {
  options.value = await fetchRows(keyword)
}

// 首次聚焦/回显：拉一批候选；已有值时按值精确查回标签
async function ensureInit() {
  if (inited.value) return
  inited.value = true
  const hasVal = props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== ''
  const rows = await fetchRows('', hasVal ? props.modelValue : undefined)
  if (hasVal && !rowCache.has(props.modelValue)) {
    options.value = rows   // 值已失效也至少展示首批候选
    return
  }
  const merged = hasVal ? [toOpt(rowCache.get(props.modelValue)), ...rows.filter((o) => o.value !== props.modelValue)] : rows
  options.value = merged
}

function onChange(val) {
  emit('update:modelValue', val)
  const row = rowCache.get(val)
  if (row) emit('carry', row)
}
</script>
