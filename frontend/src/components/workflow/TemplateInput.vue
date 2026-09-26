<template>
  <div class="tpl-input">
    <el-input ref="inp" type="textarea" :rows="rows" :model-value="modelValue" :placeholder="placeholder"
      @update:model-value="$emit('update:modelValue', $event)" />
    <div class="bar">
      <VariablePicker :groups="vars" @insert="insert" />
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import VariablePicker from './VariablePicker.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  rows: { type: Number, default: 3 },
  placeholder: { type: String, default: '' },
  vars: { type: Array, default: () => [] },   // VariablePicker 的分组变量
})
const emit = defineEmits(['update:modelValue'])

const inp = ref(null)

// 在光标处插入表达式；点击弹出层后输入框已失焦，但 selectionStart 仍然保留
function insert(expr) {
  const el = inp.value?.textarea || inp.value?.$el?.querySelector('textarea')
  const v = props.modelValue || ''
  const start = el?.selectionStart ?? v.length
  const end = el?.selectionEnd ?? start
  emit('update:modelValue', v.slice(0, start) + expr + v.slice(end))
  nextTick(() => {
    if (!el) return
    el.focus()
    el.selectionStart = el.selectionEnd = start + expr.length
  })
}
</script>

<style scoped>
.tpl-input { width: 100%; }
.bar { display: flex; justify-content: flex-end; margin-top: 2px; }
</style>
