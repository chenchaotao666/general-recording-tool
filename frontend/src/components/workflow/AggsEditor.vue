<template>
  <div class="aggs-editor">
    <div v-for="(a, i) in rows" :key="i" class="agg-row">
      <el-select v-model="a.op" size="small" class="op" @change="sync">
        <el-option v-for="[v, l] in AGG_OPS" :key="v" :label="l" :value="v" />
      </el-select>
      <template v-if="a.op !== 'count'">
        <!-- 字段：有表字段时下拉选（allow-create 仍可手输），不再配选择图标；没有时退回输入框 + 选择面板 -->
        <el-select v-if="fields.length" v-model="a.field" size="small" class="f" filterable allow-create
          default-first-option placeholder="选择字段" @change="sync">
          <el-option v-for="f in fields" :key="f.field_name" :label="`${f.label}（${f.field_name}）`" :value="f.field_name" />
          <el-option label="ID" value="id" />
        </el-select>
        <el-input v-else v-model="a.field" size="small" class="f" placeholder="字段名" @input="sync" />
      </template>
      <el-input v-model="a.title" size="small" class="t" placeholder="显示名（可选）" @input="sync" />
      <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
    </div>
    <el-button link type="primary" size="small" @click="add">+ 添加统计项</el-button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },   // [{op, field?, title?}]
  fields: { type: Array, default: () => [] },        // 上游表字段（供字段下拉）
})
const emit = defineEmits(['update:modelValue'])

const AGG_OPS = [
  ['count', '计数'], ['sum', '求和'], ['avg', '平均'],
  ['max', '最大'], ['min', '最小'], ['count_distinct', '去重计数'],
]

const rows = ref((props.modelValue || []).map((a) => ({ ...a })))
watch(() => props.modelValue, (v) => {
  const cur = rows.value.map((r) => ({ ...r, title: r.title || undefined }))
  if (JSON.stringify(cur) !== JSON.stringify(v || [])) {
    rows.value = (v || []).map((a) => ({ ...a }))
  }
})

function add() {
  rows.value.push({ op: 'count', field: undefined, title: '' })
  sync()
}
function sync() {
  emit('update:modelValue', rows.value.map((r) => {
    const out = { op: r.op }
    if (r.op !== 'count' && r.field) out.field = r.field
    if (r.title?.trim()) out.title = r.title.trim()
    return out
  }))
}
</script>

<style scoped>
.agg-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.op { width: 100px; flex-shrink: 0; }
.f { flex: 1 1 110px; min-width: 100px; }
.t { flex: 1 1 90px; min-width: 80px; }
</style>
