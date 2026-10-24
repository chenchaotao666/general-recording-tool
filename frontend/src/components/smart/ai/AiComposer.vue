<template>
  <!-- AI 输入框（参照 添加列/AI字段：AI-分类-编辑.png / AI-自定义字段.png）：
       顶部提示条（可选）+ 富文本输入（字段以 chip 内嵌，可 ✕ 删除）+ 「⊕ 插入字段」+ 发送箭头。
       输入 @ 也能呼出字段列表；Enter 发送，Shift+Enter 换行。
       发送产物：{ inputFields: [field_name…]（按出现顺序去重）, instruction: 文本（字段写作 [字段名]） } -->
  <div class="aic" :class="{ compact }">
    <div v-if="hint" class="aic-hint"><StIcon name="info" :size="16" class="aic-hint-ico" />{{ hint }}</div>
    <div ref="editorRef" class="aic-editor st-field-rich-editor" :contenteditable="!disabled" :data-ph="placeholder"
         :class="{ empty: isEmpty }" @input="onInput" @beforeinput="onBeforeInput" @keydown.stop="onKeydown" @mousedown="onEditorMouseDown"
         @keyup="saveRange" @mouseup="saveRange" @blur="saveRange" @paste="onPaste" />
    <div class="aic-foot">
      <div ref="pickerTriggerRef" class="aic-ins-wrap">
        <el-popover :visible="picker" placement="top-start" :width="256" :teleported="true" :show-arrow="false"
                    :hide-after="0" :popper-options="pickerPopperOptions" popper-class="aic-field-picker-pop"
                    :popper-style="{ padding: '8px', maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100dvh - 24px)', overflow: 'hidden' }">
          <template #reference>
        <button class="st-button aic-ins" type="button" :disabled="disabled" @mousedown.prevent @click="togglePicker"><StIcon name="plus-circle" :size="16" />插入字段</button>
          </template>
        <div v-if="picker" ref="pickerRef" class="aic-pick" @mousedown.prevent>
          <input ref="kwRef" v-model="kw" class="st-control st-control--small st-control--native aic-pick-kw" placeholder="搜索字段" @keydown.stop="onPickKey" />
          <div class="aic-pick-list">
            <div v-for="(f, i) in pickList" :key="f.field_name" class="aic-pick-item" :class="{ on: i === pickIdx }"
                 @mouseenter="pickIdx = i" @click="pick(f)">
              <StIcon :name="iconOf(f)" :size="15" class="aic-pick-ico" />{{ f.label }}
            </div>
            <div v-if="!pickList.length" class="aic-pick-none">没有匹配的字段</div>
          </div>
        </div>
        </el-popover>
      </div>
      <div class="aic-send-actions">
      <button class="st-button st-button--primary aic-send" type="button" :class="{ on: canSend, 'with-label': sendLabel }" :disabled="!canSend" :aria-label="sendLabel || '发送'" @click="send">
        <span v-if="sendLabel">{{ sendLabel }}</span>
        <StIcon v-else name="arrow-right" :size="18" :stroke-width="2" />
      </button>
      <el-dropdown v-if="secondarySendLabel" trigger="click" :disabled="!canSend" @command="sendSecondary">
        <button class="st-button st-button--primary aic-send-more" type="button" :disabled="!canSend" aria-label="更多生成选项"><StIcon name="chevron-down" :size="14" /></button>
        <template #dropdown><el-dropdown-menu><el-dropdown-item command="secondary">{{ secondarySendLabel }}</el-dropdown-item></el-dropdown-menu></template>
      </el-dropdown>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import '../../../smart/fieldRichText.css'
import StIcon from '../icons/StIcon.vue'
import { FIELD_TYPE_ICONS, fieldIconName } from '../../../smart/registry/fieldIcons.js'

const props = defineProps({
  disabled: Boolean,
  secondarySendLabel: { type: String, default: '' },
  enterToSend: { type: Boolean, default: true },
  fields: { type: Array, default: () => [] },
  hint: { type: String, default: '' },
  placeholder: { type: String, default: '选择字段或补充描述' },
  allowEmpty: { type: Boolean, default: false },   // 修改模式：允许空发送（用当前配置重新生成）
  compact: { type: Boolean, default: false },      // 紧凑版（嵌在编辑面板底部）
  sendLabel: { type: String, default: '' },
  initialText: { type: String, default: '' },
  initialFields: { type: Array, default: () => [] },
})
const emit = defineEmits(['send', 'send-secondary', 'change'])

const editorRef = ref(null)
const kwRef = ref(null)
const pickerRef = ref(null)
const pickerTriggerRef = ref(null)
const pickerPopperOptions = { strategy: 'fixed', modifiers: [
  { name: 'flip', options: { fallbackPlacements: ['bottom-start', 'top-end', 'bottom-end'], padding: 12 } },
  { name: 'preventOverflow', options: { padding: 12, boundary: [], rootBoundary: 'viewport', altAxis: true, tether: false } },
] }
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
watch(() => props.disabled, disabled => { if (disabled) picker.value = false })
const canSend = computed(() => !props.disabled && (hasContent.value || props.allowEmpty))

function chipHtml(f) {
  const svg = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"
    stroke-linecap="round" stroke-linejoin="round">${FIELD_TYPE_ICONS[iconOf(f)] || FIELD_TYPE_ICONS.text}</svg>`
  const esc = String(f.label).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
  return `<span class="aic-chip st-field-rich-chip" contenteditable="false" data-fn="${f.field_name}" data-label="${esc}">${svg}<span>${esc}</span><i class="aic-chip-x" aria-label="移除">×</i></span>`
}

function refresh(record = true) {
  const el = editorRef.value
  if (!el) return
  const text = (el.innerText ?? el.textContent ?? '').replace(/​/g, '').trim()
  const chips = el.querySelectorAll('.aic-chip').length
  hasContent.value = !!text || chips > 0
  isEmpty.value = !text && !chips
  emit('change', serialize())
  if (record) rememberEdit()
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
  editHistory.length = 0; historyIndex = -1
  refresh()
}
// One history for native typing and explicit atomic-field/line-break edits.
// Native contenteditable undo cannot reliably track Range-based corrections.
const editHistory = []
let historyIndex = -1
function selectionSnapshot() {
  const root = editorRef.value, sel = window.getSelection()
  if (!sel?.rangeCount || !root?.contains(sel.anchorNode) || !root.contains(sel.focusNode)) return null
  const path = node => {
    const steps = []
    while (node !== root) { steps.unshift([...node.parentNode.childNodes].indexOf(node)); node = node.parentNode }
    return steps
  }
  return { anchor: path(sel.anchorNode), anchorOffset: sel.anchorOffset, focus: path(sel.focusNode), focusOffset: sel.focusOffset }
}
function rememberEdit() {
  if (!editorRef.value) return
  const html = editorRef.value.innerHTML
  if (editHistory[historyIndex]?.html === html) return
  editHistory.splice(historyIndex + 1)
  editHistory.push({html, selection: selectionSnapshot()})
  if (editHistory.length > 100) editHistory.shift()
  historyIndex = editHistory.length - 1
}
function restoreEdit(direction) {
  const target = historyIndex + direction
  if (!editHistory[target]) return
  historyIndex = target
  const state = editHistory[target], root = editorRef.value
  root.innerHTML = state.html
  root.focus()
  const point = path => path.reduce((node, index) => node?.childNodes[index], root)
  const saved = state.selection
  if (saved && point(saved.anchor) && point(saved.focus)) {
    window.getSelection().setBaseAndExtent(point(saved.anchor), saved.anchorOffset, point(saved.focus), saved.focusOffset)
  } else placeCaretEnd()
  refresh(false)
  saveRange()
}
function saveRange() {
  const sel = window.getSelection()
  if (sel?.rangeCount && editorRef.value?.contains(sel.anchorNode)) {
    range = sel.getRangeAt(0).cloneRange()
    const state = editHistory[historyIndex]
    if (state?.html === editorRef.value.innerHTML) state.selection = selectionSnapshot()
  }
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
  // A text caret anchor keeps Chromium from sizing the caret from the atomic
  // inline-flex box. It is ignored by serialization and atomic deletion.
  document.execCommand('insertHTML', false, chipHtml(f).replace('class="aic-chip st-field-rich-chip"', 'class="aic-chip st-field-rich-chip" data-inserting="true"') + '\u200b')
  const inserted = el.querySelector('[data-inserting]')
  if (inserted) {
    inserted.removeAttribute('data-inserting')
    const after = document.createRange()
    const anchor = inserted.nextSibling
    if (anchor?.nodeType === 3 && anchor.data.startsWith('\u200b')) after.setStart(anchor, 1)
    else after.setStartAfter(inserted)
    after.collapse(true)
    sel.removeAllRanges()
    sel.addRange(after)
  }
  saveRange()
  refresh()
}

function togglePicker() {
  if (props.disabled) return
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

let breaksBeforeDelete = null
function onInput(e) {
  if (breaksBeforeDelete) {
    // Chromium inserts a placeholder BR when deleting the last text before an
    // atomic field. It must not become an extra user-authored line break.
    for (const br of editorRef.value.querySelectorAll('br')) {
      if (!breaksBeforeDelete.has(br)) br.remove()
    }
    breaksBeforeDelete = null
  }
  refresh()
  saveRange()
  if (e.data === '@') { atTrigger = true; picker.value = true; kw.value = ''; pickIdx.value = 0; nextTick(() => kwRef.value?.focus()) }
}
function onKeydown(e) {
  saveRange()
  if (!props.disabled && !e.isComposing && (e.ctrlKey || e.metaKey) && ['z', 'y'].includes(e.key.toLowerCase())) {
    e.preventDefault()
    restoreEdit(e.key.toLowerCase() === 'y' || e.shiftKey ? 1 : -1)
    return
  }
  breaksBeforeDelete = ['Backspace', 'Delete'].includes(e.key)
    ? new Set(editorRef.value.querySelectorAll('br')) : null
  if (!props.disabled && !e.isComposing && ['Home', 'End'].includes(e.key)
      && !e.ctrlKey && !e.metaKey && !e.altKey) {
    if (moveToLineEdge(e.key === 'Home', e.shiftKey)) { e.preventDefault(); return }
  }
  if (!props.disabled && !e.isComposing && !e.ctrlKey && !e.metaKey && !e.altKey
      && ['ArrowLeft', 'ArrowRight'].includes(e.key) && handleAdjacentField(e.key === 'ArrowLeft', true, e.shiftKey)) {
    e.preventDefault()
    return
  }
  if (!props.disabled && !e.isComposing && !e.ctrlKey && !e.metaKey && !e.altKey
      && (e.key === 'Backspace' || e.key === 'Delete') && handleAdjacentField(e.key === 'Backspace')) {
    e.preventDefault()
    return
  }
  if (e.key !== 'Enter' || e.isComposing || props.disabled) return
  e.preventDefault()
  if (props.enterToSend && !e.shiftKey) { send(); return }
  // Native insertParagraph creates nested DIVs whose line breaks can be counted
  // twice. Keep the rich-text field chips, but insert a plain line break instead.
  document.execCommand('insertLineBreak', false)
  refresh()
  saveRange()
}
function moveToLineEdge(start, extend) {
  const root = editorRef.value, selection = window.getSelection()
  if (!selection?.rangeCount || !root.contains(selection.focusNode)) return false
  const chars = [], points = [[root, 0]]
  function walk(parent) {
    for (const [index, node] of [...parent.childNodes].entries()) {
      if (node.nodeType === 3) {
        for (let i = 0; i < node.data.length; i++) {
          if (node.data[i] === '\u200b') continue
          chars.push(node.data[i]); points.push([node, i + 1])
        }
      } else if (node.classList?.contains('aic-chip')) {
        chars.push('\ufffc'); points.push([parent, index + 1])
      } else if (node.nodeName === 'BR') {
        chars.push('\n'); points.push([parent, index + 1])
      } else walk(node)
    }
  }
  walk(root)
  const caret = document.createRange()
  caret.setStart(selection.focusNode, selection.focusOffset); caret.collapse(true)
  let index = 0
  for (let i = 0; i < points.length; i++) {
    const point = document.createRange()
    point.setStart(...points[i]); point.collapse(true)
    if (point.compareBoundaryPoints(Range.START_TO_START, caret) <= 0) index = i
  }
  let target = index
  if (start) { while (target > 0 && chars[target - 1] !== '\n') target-- }
  else { while (target < chars.length && chars[target] !== '\n') target++ }
  const [node, offset] = points[target]
  if (extend) selection.extend(node, offset)
  else selection.collapse(node, offset)
  saveRange()
  return true
}
let deletingChip = false
function onBeforeInput(event) {
  if (props.disabled || deletingChip) return
  if (event.inputType === 'historyUndo' || event.inputType === 'historyRedo') {
    event.preventDefault(); restoreEdit(event.inputType === 'historyUndo' ? -1 : 1); return
  }
  if (event.inputType.startsWith('delete')) breaksBeforeDelete = new Set(editorRef.value.querySelectorAll('br'))
  if (['deleteContentBackward', 'deleteContentForward'].includes(event.inputType)
      && handleAdjacentField(event.inputType === 'deleteContentBackward')) event.preventDefault()
}
function handleAdjacentField(backward, moveOnly = false, extend = false) {
  const selection = window.getSelection()
  if (!selection?.rangeCount || !selection.isCollapsed) return false
  const caret = selection.getRangeAt(0)
  const root = editorRef.value
  if (!root?.contains(caret.startContainer)) return false
  let node = caret.startContainer
  let insideChip = (node.nodeType === 1 ? node : node.parentElement)?.closest?.('.aic-chip')
  const offset = caret.startOffset
  const meaningful = text => text.replace(/\u200b/g, '').length > 0
  const beside = current => {
    while (current && current !== root) {
      const sibling = backward ? current.previousSibling : current.nextSibling
      if (sibling) return sibling
      // Do not delete across a paragraph boundary.
      if (current.nodeName === 'DIV' || current.nodeName === 'P') return null
      current = current.parentNode
    }
    return null
  }
  if (insideChip) {
    const prefix = document.createRange()
    prefix.selectNodeContents(insideChip)
    prefix.setEnd(node, offset)
    const atEnd = prefix.toString().length > 0
    if ((backward && !atEnd) || (!backward && atEnd)) {
      const boundary = document.createRange()
      if (atEnd) boundary.setStartAfter(insideChip)
      else boundary.setStartBefore(insideChip)
      boundary.collapse(true)
      selection.removeAllRanges()
      selection.addRange(boundary)
      saveRange()
      // Let normal text deletion continue from the corrected boundary.
      return false
    }
    node = insideChip
  } else if (node.nodeType === 3) {
    const adjacent = backward ? node.data[offset - 1] : node.data[offset]
    if (!moveOnly && adjacent === '\n') {
      const lineBreak = caret.cloneRange()
      if (backward) lineBreak.setStart(node, offset - 1)
      else lineBreak.setEnd(node, offset + 1)
      selection.removeAllRanges(); selection.addRange(lineBreak)
      deletingChip = true
      try {
        lineBreak.deleteContents()
        lineBreak.collapse(true)
        selection.removeAllRanges(); selection.addRange(lineBreak)
      } finally { deletingChip = false }
      refresh(); saveRange()
      return true
    }
    if (meaningful(backward ? node.data.slice(0, offset) : node.data.slice(offset))) return false
    node = beside(node)
  } else {
    node = node.childNodes[backward ? offset - 1 : offset] || beside(node)
  }
  while (node?.nodeType === 3 && !meaningful(node.data)) node = beside(node)
  if (!moveOnly && node?.nodeName === 'BR') {
    const lineBreak = document.createRange()
    lineBreak.selectNode(node)
    selection.removeAllRanges(); selection.addRange(lineBreak)
    deletingChip = true
    try { document.execCommand('delete', false) } finally { deletingChip = false }
    refresh(); saveRange()
    return true
  }
  if (!node?.classList?.contains('aic-chip')) return false
  if (moveOnly) {
    const target = document.createRange()
    const text = backward ? node.previousSibling : node.nextSibling
    if (text?.nodeType === 3) {
      const offset = backward ? text.data.length : (text.data.match(/^\u200b*/)?.[0].length || 0)
      target.setStart(text, offset)
    } else if (backward) target.setStartBefore(node)
    else target.setStartAfter(node)
    target.collapse(true)
    if (extend) selection.extend(target.startContainer, target.startOffset)
    else {
      selection.removeAllRanges()
      selection.addRange(target)
    }
    saveRange()
    return true
  }
  const removal = caret.cloneRange()
  if (insideChip) removal.selectNode(node)
  else if (backward) removal.setStartBefore(node)
  else removal.setEndAfter(node)
  selection.removeAllRanges()
  selection.addRange(removal)
  // Native editing command preserves the browser's undo history.
  deletingChip = true
  try { document.execCommand('delete', false) } finally { deletingChip = false }
  refresh()
  saveRange()
  return true
}
// Like the formula editor, clicking a field selects the entire atomic chip.
function onEditorMouseDown(e) {
  if (props.disabled || e.button !== 0) return
  const chip = e.target.closest?.('.aic-chip')
  if (!chip) return
  e.preventDefault()
  editorRef.value.focus()
  const selected = document.createRange()
  selected.selectNode(chip)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(selected)
  if (e.target.closest('.aic-chip-x')) {
    document.execCommand('delete', false)
    refresh()
  }
  saveRange()
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
      else { if (['DIV', 'P'].includes(n.nodeName) && out.length && !out.join('').endsWith('\n')) out.push('\n'); walk(n) }
    }
  }
  walk(editorRef.value)
  return { inputFields: [...new Set(fns)], instruction: out.join('').trim() }
}
function sendSecondary() { if (canSend.value) emit('send-secondary', serialize()) }
function send() {
  if (!canSend.value) return
  emit('send', serialize())
}
function clear() { if (editorRef.value) editorRef.value.innerHTML = ''; refresh() }

function onDocDown(e) {
  if (picker.value && !pickerTriggerRef.value?.contains(e.target) && !pickerRef.value?.contains(e.target)) { picker.value = false; atTrigger = false }
}
document.addEventListener('mousedown', onDocDown)
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocDown))

defineExpose({ insertField, clear, setContent, focus: () => nextTick(placeCaretEnd) })
</script>

<style scoped>
:global(.aic-field-picker-pop[class*="-leave-active"]) { pointer-events: none; }
.aic { background: #fff; border-radius: 16px; padding: 10px 12px 12px; display: flex; flex-direction: column; border: 1px solid #EBECEE; }
.aic.compact { padding: 6px 10px 8px; border-radius: 14px; }
.aic.compact .aic-editor { min-height: 26px; padding: 8px 4px 2px; font-size: var(--st-font-size); }
.aic-send-actions { display: flex; align-items: stretch; gap: 2px; }
.aic-send-more { height: 100%; min-height: 28px; padding: 0 8px; }
.aic.compact .aic-foot { margin-top: 4px; }
.aic.compact .aic-ins { height: 30px; font-size: var(--st-font-size); padding: 0 10px; }
.aic.compact .aic-send { width: 34px; height: 34px; border-radius: 8px; }
.aic .aic-send.with-label { width: auto; padding: 0 14px; white-space: nowrap; font-size: var(--st-font-size); }
.aic-hint { display: flex; align-items: center; gap: 6px; background: #F5F6F7; border-radius: 10px; padding: 9px 12px;
            font-size: var(--st-font-size); color: var(--st-text-2); }
.aic-hint-ico { color: var(--st-primary); }
.aic-editor { position: relative; min-height: 64px; max-height: 160px; overflow-y: auto; outline: none; font-size: var(--st-font-size);
              color: var(--st-text-2); }
.aic-editor.empty::before { content: attr(data-ph); position: absolute; inset: 0; color: #B5B9C0; pointer-events: none; }
.aic.compact .aic-editor.empty::before { inset: 8px 4px 2px; }
.aic-editor :deep(.aic-chip) { user-select: text; }
.aic-editor :deep(.aic-chip svg) { color: var(--st-text-2); }
.aic-editor :deep(.aic-chip-x) { font-style: normal; color: var(--st-text-3); cursor: pointer; margin-left: 2px; font-size: var(--st-font-size); }
.aic-editor :deep(.aic-chip-x:hover) { color: var(--st-text-2); }
.aic-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.aic-ins-wrap { position: relative; }
.aic-ins { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 12px; border: 1px solid #E3E5E8;
           border-radius: 8px; background: #fff; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.aic-ins:hover { background: #F5F6F7; color: var(--st-text-2); }
.aic-pick { display: flex; flex-direction: column; min-height: 0; max-height: calc(100dvh - 42px); background: #fff; }
.aic-pick-kw { width: 100%; box-sizing: border-box; height: 32px; border: 1px solid #E3E5E8; border-radius: 6px; padding: 0 10px;
               outline: none; font-size: var(--st-font-size); margin-bottom: 6px; }
.aic-pick-kw:focus { border-color: var(--st-primary); }
.aic-pick-list { min-height: 0; max-height: 240px; overflow-y: auto; }
.aic-pick-kw { flex-shrink: 0; }
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
