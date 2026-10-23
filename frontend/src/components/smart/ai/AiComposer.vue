<template>
  <!-- AI 输入框（参照 添加列/AI字段：AI-分类-编辑.png / AI-自定义字段.png）：
       顶部提示条（可选）+ 富文本输入（字段以 chip 内嵌，可 ✕ 删除）+ 「⊕ 插入字段」+ 发送箭头。
       输入 @ 也能呼出字段列表；Enter 发送，Shift+Enter 换行。
       发送产物：{ inputFields: [field_name…]（按出现顺序去重）, instruction: 文本（字段写作 [字段名]） } -->
  <div class="aic" :class="{ compact }">
    <div v-if="hint" class="aic-hint"><StIcon name="info" :size="16" class="aic-hint-ico" />{{ hint }}</div>
    <div ref="editorRef" class="aic-editor" contenteditable="true" :data-ph="placeholder"
         :class="{ empty: isEmpty }" @input="onInput" @keydown="onKeydown" @mousedown="onEditorMouseDown"
         @keyup="saveRange" @mouseup="saveRange" @blur="saveRange" @paste="onPaste" />
    <div class="aic-foot">
      <div class="aic-ins-wrap">
        <button class="st-button aic-ins" type="button" @mousedown.prevent @click="togglePicker"><StIcon name="plus-circle" :size="16" />插入字段</button>
        <div v-if="picker" class="aic-pick" @mousedown.prevent>
          <input ref="kwRef" v-model="kw" class="st-control st-control--small st-control--native aic-pick-kw" placeholder="搜索字段" @keydown.stop="onPickKey" />
          <div class="aic-pick-list">
            <div v-for="(f, i) in pickList" :key="f.field_name" class="aic-pick-item" :class="{ on: i === pickIdx }"
                 @mouseenter="pickIdx = i" @click="pick(f)">
              <StIcon :name="iconOf(f)" :size="15" class="aic-pick-ico" />{{ f.label }}
            </div>
            <div v-if="!pickList.length" class="aic-pick-none">没有匹配的字段</div>
          </div>
        </div>
      </div>
      <button class="st-button st-button--primary aic-send" type="button" :class="{ on: canSend, 'with-label': sendLabel }" :disabled="!canSend" :aria-label="sendLabel || '发送'" @click="send">
        <span v-if="sendLabel">{{ sendLabel }}</span>
        <StIcon v-else name="arrow-right" :size="18" :stroke-width="2" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import { FIELD_TYPE_ICONS, fieldIconName } from '../../../smart/registry/fieldIcons.js'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  hint: { type: String, default: '' },
  placeholder: { type: String, default: '选择字段或补充描述' },
  allowEmpty: { type: Boolean, default: false },   // 修改模式：允许空发送（用当前配置重新生成）
  compact: { type: Boolean, default: false },      // 紧凑版（嵌在编辑面板底部）
  sendLabel: { type: String, default: '' },
  initialText: { type: String, default: '' },
  initialFields: { type: Array, default: () => [] },
})
const emit = defineEmits(['send', 'change'])

const editorRef = ref(null)
const kwRef = ref(null)
const isEmpty = ref(true)
const hasContent = ref(false)
const picker = ref(false)
watch(() => [props.initialText, props.initialFields], async ([text, fields]) => {
  await nextTick()
  setContent(text, fields)
}, { immediate: true, deep: true })
const kw = ref('')
const pickIdx = ref(0)
let range = null
let atTrigger = false   // 由 @ 呼出：选中后把 @ 删掉

const iconOf = fieldIconName
const pickList = computed(() => {
  const k = kw.value.trim()
  return props.fields.filter(f => !k || f.label.includes(k))
})
const canSend = computed(() => hasContent.value || props.allowEmpty)

function chipHtml(f) {
  const svg = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"
    stroke-linecap="round" stroke-linejoin="round">${FIELD_TYPE_ICONS[iconOf(f)] || FIELD_TYPE_ICONS.text}</svg>`
  const esc = String(f.label).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
  return `<span class="aic-chip" contenteditable="false" data-fn="${f.field_name}" data-label="${esc}">${svg}<span>${esc}</span><i class="aic-chip-x" aria-label="移除">×</i></span>`
}

function refresh() {
  const el = editorRef.value
  if (!el) return
  const text = (el.innerText ?? el.textContent ?? '').replace(/​/g, '').trim()
  const chips = el.querySelectorAll('.aic-chip').length
  hasContent.value = !!text || chips > 0
  isEmpty.value = !text && !chips
  emit('change', serialize())
}
function setContent(text = '', fieldNames = []) {
  const el = editorRef.value
  if (!el) return
  el.replaceChildren()
  const fields = fieldNames.map(fn => props.fields.find(f => f.field_name === fn)).filter(Boolean)
  const used = new Set()
  const appendChip = f => {
    const tpl = document.createElement('template')
    tpl.innerHTML = chipHtml(f)
    el.append(tpl.content, document.createTextNode(' '))
    used.add(f.field_name)
  }
  let offset = 0
  for (const match of text.matchAll(/\[([^\]]+)\]/g)) {
    const f = fields.find(f => f.label === match[1])
    if (!f) continue
    el.append(document.createTextNode(text.slice(offset, match.index)))
    appendChip(f)
    offset = match.index + match[0].length
  }
  el.append(document.createTextNode(text.slice(offset)))
  for (const f of fields) if (!used.has(f.field_name)) {
    el.append(document.createTextNode(' '))
    appendChip(f)
  }
  range = null
  refresh()
}
function saveRange() {
  const sel = window.getSelection()
  if (sel?.rangeCount && editorRef.value?.contains(sel.anchorNode)) range = sel.getRangeAt(0).cloneRange()
}
function placeCaretEnd() {
  const el = editorRef.value
  el.focus()
  const r = document.createRange()
  r.selectNodeContents(el)
  r.collapse(false)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(r)
  range = r.cloneRange()
}

function insertField(f) {
  const el = editorRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection()
  if (range && el.contains(range.startContainer)) { sel.removeAllRanges(); sel.addRange(range) } else placeCaretEnd()
  if (atTrigger) {   // 删掉触发用的 @
    const r = sel.getRangeAt(0)
    const n = r.startContainer
    const off = r.startOffset
    if (n.nodeType === 3 && off > 0 && n.data[off - 1] === '@') {
      n.deleteData(off - 1, 1)
      r.setStart(n, off - 1)
      r.collapse(true)
    }
    atTrigger = false
  }
  const r = sel.getRangeAt(0)
  r.deleteContents()
  const tpl = document.createElement('template')
  tpl.innerHTML = chipHtml(f) + '​'
  const frag = tpl.content
  const last = frag.lastChild
  r.insertNode(frag)
  const nr = document.createRange()
  nr.setStartAfter(last)
  nr.collapse(true)
  sel.removeAllRanges()
  sel.addRange(nr)
  range = nr.cloneRange()
  refresh()
}

function togglePicker() {
  picker.value = !picker.value
  if (picker.value) { kw.value = ''; pickIdx.value = 0; nextTick(() => kwRef.value?.focus()) }
  else atTrigger = false
}
function pick(f) { picker.value = false; insertField(f) }
function onPickKey(e) {
  if (e.key === 'ArrowDown') { e.preventDefault(); pickIdx.value = Math.min(pickList.value.length - 1, pickIdx.value + 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); pickIdx.value = Math.max(0, pickIdx.value - 1) }
  else if (e.key === 'Enter') { e.preventDefault(); if (pickList.value[pickIdx.value]) pick(pickList.value[pickIdx.value]) }
  else if (e.key === 'Escape') { e.preventDefault(); picker.value = false; atTrigger = false; editorRef.value?.focus() }
}

function onInput(e) {
  refresh()
  saveRange()
  if (e.data === '@') { atTrigger = true; picker.value = true; kw.value = ''; pickIdx.value = 0; nextTick(() => kwRef.value?.focus()) }
}
function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send() }
}
// chip 的 ✕：删除整个 chip
function onEditorMouseDown(e) {
  const x = e.target.closest?.('.aic-chip-x')
  if (!x) return
  e.preventDefault()
  x.closest('.aic-chip')?.remove()
  refresh()
}
// 粘贴只取纯文本
function onPaste(e) {
  e.preventDefault()
  const t = e.clipboardData?.getData('text/plain') || ''
  document.execCommand('insertText', false, t)
}

function serialize() {
  const out = []
  const fns = []
  const walk = (node) => {
    for (const n of node.childNodes) {
      if (n.nodeType === 3) out.push(n.data.replace(/​/g, ''))
      else if (n.classList?.contains('aic-chip')) { out.push(`[${n.dataset.label}]`); fns.push(n.dataset.fn) }
      else if (n.nodeName === 'BR') out.push('\n')
      else { if (n.nodeName === 'DIV' && out.length) out.push('\n'); walk(n) }
    }
  }
  walk(editorRef.value)
  return { inputFields: [...new Set(fns)], instruction: out.join('').trim() }
}
function send() {
  if (!canSend.value) return
  emit('send', serialize())
}
function clear() { if (editorRef.value) editorRef.value.innerHTML = ''; refresh() }

function onDocDown(e) {
  if (picker.value && !e.target.closest?.('.aic-ins-wrap')) { picker.value = false; atTrigger = false }
}
document.addEventListener('mousedown', onDocDown)
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocDown))

defineExpose({ insertField, clear, setContent, focus: () => nextTick(placeCaretEnd) })
</script>

<style scoped>
.aic { background: #fff; border-radius: 16px; padding: 10px 12px 12px; display: flex; flex-direction: column; border: 1px solid #EBECEE; }
.aic.compact { padding: 6px 10px 8px; border-radius: 14px; }
.aic.compact .aic-editor { min-height: 26px; padding: 8px 4px 2px; font-size: var(--st-font-size); }
.aic.compact .aic-foot { margin-top: 4px; }
.aic.compact .aic-ins { height: 30px; font-size: var(--st-font-size); padding: 0 10px; }
.aic.compact .aic-send { width: 34px; height: 34px; border-radius: 8px; }
.aic .aic-send.with-label { width: auto; padding: 0 14px; white-space: nowrap; font-size: var(--st-font-size); }
.aic-hint { display: flex; align-items: center; gap: 6px; background: #F5F6F7; border-radius: 10px; padding: 9px 12px;
            font-size: var(--st-font-size); color: var(--st-text-2); }
.aic-hint-ico { color: var(--st-primary); }
.aic-editor { min-height: 64px; max-height: 160px; overflow-y: auto; outline: none; font-size: var(--st-font-size);
              line-height: 26px; color: var(--st-text-2); white-space: pre-wrap; word-break: break-all; }
.aic-editor.empty::before { content: attr(data-ph); color: #B5B9C0; pointer-events: none; }
.aic-editor :deep(.aic-chip) { display: inline-flex; align-items: center; gap: 4px; height: 24px; padding: 0 6px; margin: 0 3px;
                               background: #F2F3F5; border-radius: 4px; font-size: var(--st-font-size); color: var(--st-text-2);
                               vertical-align: 1px; user-select: none; line-height: 24px; }
.aic-editor :deep(.aic-chip svg) { color: var(--st-text-2); }
.aic-editor :deep(.aic-chip-x) { font-style: normal; color: var(--st-text-3); cursor: pointer; margin-left: 2px; font-size: var(--st-font-size); }
.aic-editor :deep(.aic-chip-x:hover) { color: var(--st-text-2); }
.aic-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.aic-ins-wrap { position: relative; }
.aic-ins { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 12px; border: 1px solid #E3E5E8;
           border-radius: 8px; background: #fff; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.aic-ins:hover { background: #F5F6F7; color: var(--st-text-2); }
.aic-pick { position: absolute; left: 0; bottom: calc(100% + 6px); width: 240px; background: #fff; border-radius: 10px;
            box-shadow: 0 6px 24px rgba(0, 0, 0, .14); padding: 8px; z-index: 10; }
.aic-pick-kw { width: 100%; box-sizing: border-box; height: 32px; border: 1px solid #E3E5E8; border-radius: 6px; padding: 0 10px;
               outline: none; font-size: var(--st-font-size); margin-bottom: 6px; }
.aic-pick-kw:focus { border-color: var(--st-primary); }
.aic-pick-list { max-height: 240px; overflow-y: auto; }
.aic-pick-item { display: flex; align-items: center; gap: 8px;  padding: 0 8px; border-radius: 6px; font-size: var(--st-font-size);
                 color: var(--st-text-2); cursor: pointer;  height: var(--st-list-item-height); box-sizing: border-box; }
.aic-pick-item.on { background: #F2F3F5; }
.aic-pick-ico { color: var(--st-text-2); }
.aic-pick-none { padding: 14px; text-align: center; font-size: var(--st-font-size); color: var(--st-text-3); }
.aic-send { width: 42px; height: 42px; border-radius: 10px; border: none; background: #B5CDF8; color: #fff; display: inline-flex;
            align-items: center; justify-content: center; cursor: not-allowed; }
.aic-send.on { background: var(--st-primary); cursor: pointer; }
.aic-send.on:hover { background: var(--st-primary-hover, #255BD0); }
</style>
