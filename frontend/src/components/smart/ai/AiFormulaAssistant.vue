<template>
  <section class="afa">
    <div class="afa-composer">
    <el-input id="formula-ai-request" aria-label="描述你想计算的结果" ref="input" v-model="prompt" type="textarea" :rows="1" :autosize="{ minRows: 1 }" @focus="$emit('focus')" placeholder="例如：单价乘以数量，再打九折" @keydown.ctrl.enter.prevent="generate" @keydown.meta.enter.prevent="generate" />
    <div class="afa-actions"><span>Ctrl + Enter 生成</span><el-button class="st-button st-button--primary" type="primary" :loading="loading" :disabled="!prompt.trim()" @click="generate">{{ loading ? '生成中' : result ? '重新生成' : '生成公式' }}</el-button></div>
    </div>
    <p v-if="error" role="alert" class="afa-error">{{ error }}</p>
    <template v-if="result">
      <div class="afa-result-heading"><strong>生成结果</strong><el-button type="primary" :disabled="loading" @click="$emit('apply', result)">使用此公式</el-button></div>
      <code class="afa-code">{{ result.display || result.formula }}</code>
      <p class="afa-explanation">{{ result.explanation }}</p>
    </template>
  </section>
</template>
<script setup>
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { smartAiGenerateFormula } from '../../../api/index.js'
const props = defineProps({ active: Boolean, tableId: Number })
defineEmits(['focus', 'apply'])
defineExpose({ insertField })
const input = ref(null), prompt = ref(''), result = ref(null), loading = ref(false), error = ref('')
let alive = true
onBeforeUnmount(() => { alive = false })
watch(() => props.active, async active => { if (active) { await nextTick(); input.value?.focus() } }, { immediate: true })
async function insertField(field) {
  const el = input.value?.textarea
  const start = el?.selectionStart ?? prompt.value.length, end = el?.selectionEnd ?? start
  const text = `[${field.label}]`
  prompt.value = prompt.value.slice(0, start) + text + prompt.value.slice(end)
  await nextTick()
  input.value?.focus()
  el?.setSelectionRange(start + text.length, start + text.length)
}
async function generate() {
  if (loading.value || !prompt.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    const response = await smartAiGenerateFormula(props.tableId, prompt.value.trim())
    if (alive) result.value = response
  } catch (e) { if (alive) error.value = e.message || '生成失败，请重试' }
  finally { if (alive) loading.value = false }
}
</script>
<style scoped>
.afa { display: flex; flex-direction: column; gap: 6px; font-size: var(--st-font-size); }
.afa-result-heading, .afa-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.afa-composer { background: #fff; border: 1px solid var(--st-border); border-radius: 8px; padding: 8px 12px; }
.afa-composer:focus-within { border-color: var(--st-primary); box-shadow: 0 0 0 2px rgba(46, 107, 230, .12); }
.afa-composer :deep(.el-textarea__inner) { padding: 0; border: 0; border-radius: 0; box-shadow: none; background: transparent; resize: none; font-family: inherit; font-size: var(--st-font-size); line-height: 2; color: var(--st-text-2); }
.afa-composer :deep(.el-textarea__inner:focus), .afa-composer :deep(.el-textarea__inner:hover) { box-shadow: none; }
.afa-actions { margin-top: 4px; }
.afa :deep(.el-button) { height: 28px; padding: 0 12px; }
.afa-actions span, .afa-note { font-size: 12px; color: var(--st-text-3); }
.afa-code { padding: 6px 12px; border: 1px solid var(--st-border); border-radius: 6px; background: white; white-space: pre-wrap; overflow-wrap: anywhere; }
.afa-explanation { margin: 0; line-height: 1.5; color: var(--st-text-2); }
.afa-error { margin: 0; color: var(--el-color-danger); }
</style>
