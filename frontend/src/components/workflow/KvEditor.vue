<template>
  <div class="kv-editor">
    <div v-for="(row, i) in rows" :key="i" class="kv-row" :class="{ tall: valueTextarea }">
      <!-- 多行值：键名一行、值占满一行、操作（插入变量/删除）第三行右对齐 -->
      <template v-if="valueTextarea">
        <el-input v-model="row.key" :placeholder="keyPlaceholder" size="small" class="k" @input="sync" />
        <HlTextarea :model-value="row.value" :ref="(el) => (inputRefs[i] = el)"
          :autosize="{ minRows: 2, maxRows: 6 }" :placeholder="valuePlaceholder" class="v"
          @update:model-value="row.value = $event; sync()" />
        <div class="kv-actions">
          <VariablePicker compact title="插入变量到值" :groups="vars" @insert="insertVar(i, $event)" />
          <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
        </div>
      </template>
      <!-- 单行值：键值一行平铺 -->
      <template v-else>
        <el-input v-model="row.key" :placeholder="keyPlaceholder" size="small" class="k" @input="sync" />
        <el-input v-model="row.value" :ref="(el) => (inputRefs[i] = el)" :placeholder="valuePlaceholder"
          size="small" class="v" @input="sync" />
        <VariablePicker :groups="vars" @insert="insertVar(i, $event)" />
        <el-button link type="danger" size="small" @click="rows.splice(i, 1); sync()">删</el-button>
      </template>
    </div>
    <el-button link type="primary" size="small" @click="rows.push({ key: '', value: '' })">+ 添加一行</el-button>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import VariablePicker from './VariablePicker.vue'
import HlTextarea from './HlTextarea.vue'

// 通用键值对编辑器：HTTP 请求头/请求体（表单模式）、子流程传参等 object 配置用。
// 采过的坑都内置了：空值行不落配置 + watch 对比口径一致；presetKeys 预填在 fromObj 之后注册
const props = defineProps({
  modelValue: { type: Object, default: undefined },
  vars: { type: Array, default: () => [] },
  keyPlaceholder: { type: String, default: '键名' },
  valuePlaceholder: { type: String, default: '值，或点右侧插入变量' },
  // 预填的键清单（如子流程用到的 trigger.params 键），仅在没有任何行时生效
  presetKeys: { type: Array, default: () => [] },
  // 值用多行文本框（内容较长的场景，如子流程传参）
  valueTextarea: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const rows = ref([])
const inputRefs = ref([])

function fromObj(obj) {
  return Object.entries(obj || {}).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}
rows.value = fromObj(props.modelValue)

// 预填键行：fromObj 之后注册，避免 immediate 同步执行后被覆盖
watch(() => props.presetKeys, (keys) => {
  if (!keys?.length || rows.value.length) return
  rows.value = keys.map((k) => ({ key: k, value: '' }))
}, { immediate: true })

watch(() => props.modelValue, (v) => {
  // 仅外部变化时重建；对比口径与 sync() 一致（跳过空值行），否则未填值的行会被误重建掉
  const cur = {}
  for (const r of rows.value) if (r.key && r.value !== '') cur[r.key] = r.value
  if (JSON.stringify(cur) !== JSON.stringify(v || {})) rows.value = fromObj(v)
}, { deep: true })

function sync() {
  const obj = {}
  for (const r of rows.value) {
    if (r.key && r.value !== '') obj[r.key] = r.value
  }
  emit('update:modelValue', Object.keys(obj).length ? obj : undefined)
}

// 在光标处插入变量表达式（失焦后 selectionStart 仍保留），取不到光标就追加到末尾。
// 兼容单行 input（.input）、多行 textarea（.textarea）和高亮文本框组件（.textareaEl()）
function insertVar(i, expr) {
  const row = rows.value[i]
  if (!row) return
  const refEl = inputRefs.value[i]
  const el = refEl?.input || refEl?.textarea || refEl?.textareaEl?.() || refEl?.$el?.querySelector('input,textarea')
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
</script>

<style scoped>
.kv-editor { width: 100%; }   /* el-form-item__content 是 flex 容器，不声明宽度会收缩到内容宽 */
.kv-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
/* 多行值：无外框；键名一行、值占满一行、操作第三行右对齐。
   ⚡ 与「删」的间距与筛选条件行一致：flex gap 6px + EP 相邻按钮默认 margin-left 12px（不要覆盖掉） */
.kv-row.tall { display: block; margin-bottom: 10px; }
.kv-row.tall .k { width: 100%; margin-bottom: 6px; }
.kv-row.tall .v { width: 100%; }
.kv-row.tall .kv-actions { display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-top: 2px; }
.k { flex: 0 1 150px; min-width: 100px; }
.v { flex: 1; min-width: 100px; }
</style>
