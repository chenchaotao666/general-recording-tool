<template>
  <span class="link-cell-anchor" :class="{ selected }" @mousedown.stop @click.stop @dblclick.stop>
    <div ref="anchor" class="link-cell-trigger" @click="toggle">
      <a v-if="value?.url" :href="safeHref" target="_blank" rel="noopener noreferrer" class="link-cell-text" @click.stop="clickLink">{{ value.text || value.url }}</a>
      <CellDropdown v-if="!readonly" class="link-cell-arrow" overlay :visible="selected || opened" :open="opened" label="编辑链接" @click="toggle" />
    </div>
    <el-popover v-if="opened" :visible="opened" virtual-triggering :virtual-ref="anchor" placement="bottom-start" :width="420" :show-arrow="false" popper-class="link-cell-pop" :persistent="false">
      <form ref="panel" class="link-cell-panel" @submit.prevent="confirm" @keydown.enter="enterConfirm" @keydown.tab="enterConfirm" @mousedown.stop @click.stop @keydown.esc.stop.prevent="close(true)">
        <label class="link-edit-row"><span>显示文本</span><el-input ref="textInput" v-model="text" placeholder="显示文本" aria-label="显示文本" /></label>
        <label class="link-edit-row"><span>链接</span><el-input v-model="url" placeholder="https://" aria-label="链接" @input="error = ''" /></label>
        <div v-if="error" class="link-edit-error" role="alert">{{ error }}</div>
        <div class="link-edit-actions"><el-button @click="close(true)">取消</el-button><el-button type="primary" native-type="submit">确认</el-button></div>
      </form>
    </el-popover>
  </span>
</template>
<script setup>
import { useGridScrollCollapse } from '../../../smart/utils/useGridScrollCollapse.js'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import CellDropdown from './CellDropdown.vue'
const props = defineProps({ value: Object, selected: Boolean, readonly: Boolean, advanceOnEnter: Boolean, initialInput: String })
const emit = defineEmits(['select', 'open', 'collapse', 'cancel', 'commit', 'advance'])
const opened = ref(false), text = ref(''), url = ref(''), error = ref('')
const anchor = ref(null), panel = ref(null), textInput = ref(null)
const safeHref = computed(() => /^https?:\/\//i.test(props.value?.url || '') ? props.value.url : undefined)
async function focus() {
  if (props.readonly) return
  text.value = props.value?.text || ''; url.value = props.value?.url || 'https://'; error.value = ''
  opened.value = true; emit('open'); await nextTick(); textInput.value?.focus()
  const input = textInput.value?.input
  if (input) input.setSelectionRange(input.value.length, input.value.length)
}
watch(() => props.initialInput, async value => {
  if (value == null || props.readonly) return
  if (!opened.value) await focus()
  text.value = value
  await nextTick()
  const input = textInput.value?.input
  if (input) input.setSelectionRange(input.value.length, input.value.length)
})
function toggle() { const active = props.selected || opened.value; emit('select'); if (!active || props.readonly) return; if (opened.value) close(true); else focus() }
function clickLink(event) {
  if (!props.selected) {
    event.preventDefault(); emit('select')
  }
}
function close(keep) { opened.value = false; emit(keep ? 'collapse' : 'cancel') }
function enterConfirm(event) {
  if (event.key === 'Tab' && !props.advanceOnEnter) return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault(); event.stopPropagation()
  confirm(props.advanceOnEnter ? (event.key === 'Tab' ? (event.shiftKey ? 'left' : 'right') : event.shiftKey ? 'up' : 'down') : false)
}
function confirm(advance = false) {
  const entered = url.value.trim()
  if (!entered) { error.value = '请输入链接'; return }
  if (/^[a-z][a-z\d+.-]*:/i.test(entered) && !/^https?:\/\//i.test(entered)) { error.value = '请输入 http 或 https 链接'; return }
  const normalized = /^https?:\/\//i.test(entered) ? entered : `https://${entered}`
  try { new URL(normalized) } catch { error.value = '请输入有效链接'; return }
  emit('commit', { url: normalized, text: text.value.trim() || entered }); close(true)
  if (typeof advance === 'string') emit('advance', advance)
}
function outside(event) { if (opened.value && !anchor.value?.contains(event.target) && !panel.value?.contains(event.target)) close(false) }
watch(opened, (visible, _, onCleanup) => {
  if (!visible) return
  document.addEventListener('mousedown', outside, true)
  onCleanup(() => document.removeEventListener('mousedown', outside, true))
}, { flush: 'sync' })
onBeforeUnmount(() => document.removeEventListener('mousedown', outside, true))
defineExpose({ focus })
useGridScrollCollapse(() => opened.value, () => {
  opened.value = false
  emit('collapse')
})
</script>
<style>
.el-popper.link-cell-pop { padding: 0; border: 1px solid #e0e2e6; border-radius: 10px; box-shadow: 0 4px 16px #0002; max-width: calc(100vw - 24px); }
</style>
<style scoped>
.link-cell-anchor { display: block; width: 100%; height: 100%; }
.link-cell-trigger { position: relative; display: flex; align-items: center; height: 100%; min-height: 28px; cursor: default; }
.link-cell-anchor.selected .link-cell-trigger { cursor: pointer; }
.link-cell-text { color: var(--st-primary); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; cursor: default; font-size: var(--st-font-size); line-height: 22px; }
.link-cell-anchor.selected .link-cell-text { cursor: pointer; }
.link-cell-anchor.selected .link-cell-text:hover { text-decoration: underline; }
.link-cell-panel { padding: 26px; }
.link-edit-row { display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
.link-edit-row > span { width: 70px; flex: none; font-size: var(--st-font-size); color: var(--st-text-2); }
.link-edit-row :deep(.el-input__wrapper) { min-height: 36px; border-radius: 6px; }
.link-edit-actions { display: flex; justify-content: flex-end; gap: 16px; margin-top: 22px; }
.link-edit-actions .el-button { width: 100px; height: 36px; margin: 0; border-radius: 6px; }
.link-edit-actions .el-button:not(.el-button--primary) { background: #f2f3f5; border-color: #f2f3f5; color: var(--st-text-2); }
.link-edit-error { color: #e45b5b; font-size: var(--st-font-size); padding-left: 88px; }
</style>
