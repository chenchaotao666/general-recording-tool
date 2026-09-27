<template>
  <div class="json-input">
    <el-input ref="inp" v-model="text" type="textarea" :rows="rows"
      placeholder='JSON，如 {"title": "{nodes.q_1.count}"}（值里可插变量）' @input="onInput" />
    <div class="bar">
      <span v-if="err" class="err">{{ err }}</span>
      <el-button link type="primary" size="small" :disabled="!text.trim()" @click="format">格式化</el-button>
      <VariablePicker :groups="vars" @insert="insert" />
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import VariablePicker from './VariablePicker.vue'

// JSON 编辑器（object/array 配置用）：格式化 + 光标处插入变量
const props = defineProps({
  modelValue: { type: [Object, Array, String], default: undefined },
  rows: { type: Number, default: 5 },
  vars: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const inp = ref(null)
const text = ref('')
const err = ref('')

// 外部值变化（加载已保存配置等）→ 美化显示；与本地文本一致时不动（避免打字中光标跳动）
watch(() => props.modelValue, (v) => {
  const pretty = v === undefined || v === null ? '' : (typeof v === 'string' ? v : JSON.stringify(v, null, 2))
  if (!err.value && pretty !== text.value) {
    // 本地文本若能解析成相同 JSON 则说明只是排版不同，不打断编辑
    try {
      if (JSON.stringify(JSON.parse(text.value)) === JSON.stringify(v)) return
    } catch { /* 本地非合法 JSON，覆盖 */ }
    text.value = pretty
  }
}, { immediate: true, deep: true })

// 把 JSON.parse 的报错翻译成行列号（V8 两种文案格式都兼容：position N / line x column y）
function parseError(e) {
  const m = /position (\d+)/.exec(e.message)
  if (m) {
    const pos = Number(m[1])
    const upto = text.value.slice(0, pos)
    const line = upto.split('\n').length
    const col = pos - upto.lastIndexOf('\n')
    const reason = e.message.split(' in JSON')[0].split(' at position')[0]
    return `JSON 格式错误：第 ${line} 行第 ${col} 列附近（${reason}）`
  }
  const m2 = /line (\d+) column (\d+)/i.exec(e.message)
  if (m2) return `JSON 格式错误：第 ${m2[1]} 行第 ${m2[2]} 列附近`
  return `JSON 格式错误：${e.message}`
}

function onInput() {
  const t = text.value.trim()
  if (!t) {
    err.value = ''
    emit('update:modelValue', undefined)
    return
  }
  try {
    emit('update:modelValue', JSON.parse(t))
    err.value = ''
  } catch (e) {
    err.value = parseError(e)
  }
}

function format() {
  try {
    text.value = JSON.stringify(JSON.parse(text.value), null, 2)
    err.value = ''
    onInput()
  } catch (e) {
    err.value = `${parseError(e)}，无法格式化`
  }
}

// 光标处插入变量表达式（失焦后 selectionStart 仍保留），随后触发一次解析同步
function insert(expr) {
  const el = inp.value?.textarea || inp.value?.$el?.querySelector('textarea')
  const v = text.value || ''
  const start = el?.selectionStart ?? v.length
  const end = el?.selectionEnd ?? start
  text.value = v.slice(0, start) + expr + v.slice(end)
  onInput()
  nextTick(() => {
    if (!el) return
    el.focus()
    el.selectionStart = el.selectionEnd = start + expr.length
  })
}
</script>

<style scoped>
.json-input { width: 100%; }
.bar { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 2px; }
.err { font-size: 12px; color: #f56c6c; margin-right: auto; }
</style>
