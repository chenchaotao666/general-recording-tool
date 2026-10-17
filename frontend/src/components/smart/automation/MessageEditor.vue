<template>
  <!-- 消息内容编辑器（§11.2）：标题（加粗）+ 正文富文本，变量为可单独删除的原子胶囊；
       底栏：添加表情 / 插入变量 / ＋ 添加按钮（对齐参照 右上角工具栏-新建自动化提醒.png） -->
  <div class="me" :class="{ focus }">
    <input v-model="title" class="me-title" placeholder="消息标题" @input="emitAll" />
    <div ref="bodyRef" class="me-body" contenteditable="true" data-placeholder="请输入消息内容，可插入变量"
         @input="emitAll" @focus="focus = true" @blur="onBlur" @keydown="onKey" @click="onBodyClick" />
    <div v-if="buttons.length" class="me-buttons">
      <span v-for="(b, i) in buttons" :key="i" class="me-btn-chip">{{ b.label }}
        <span class="me-x" @click="buttons.splice(i, 1); emitAll()">✕</span></span>
    </div>
    <div class="me-bar">
      <span class="me-tool" @mousedown.prevent @click="toggleEmoji($event)"><StIcon name="emoji" :size="16" />添加表情</span>
      <span class="me-tool" @mousedown.prevent @click="openVars($event)">{x} 插入变量</span>
      <span class="me-tool me-right" @click="addButton"><StIcon name="plus" :size="15" />添加按钮</span>
    </div>
    <teleport to="body">
      <div v-if="emoji.visible || vars.visible" class="me-mask" @mousedown="closeMenus" />
      <div v-if="emoji.visible" class="me-emoji" :style="{ left: `${emoji.x}px`, top: `${emoji.y}px` }" @mousedown.prevent>
        <span v-for="e in EMOJIS" :key="e" class="me-e" @click="insertText(e)">{{ e }}</span>
      </div>
      <VarMenu v-if="vars.visible" :x="vars.x" :y="vars.y" :steps="steps" :dashboards="dashboards" @pick="insertVar" />
    </teleport>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import VarMenu from './VarMenu.vue'

const props = defineProps({
  titleValue: { type: String, default: '' },
  content: { type: Array, default: () => [] },        // [{t:'text',v}|{t:'var',var,label}|{t:'br'}]
  buttonsValue: { type: Array, default: () => [] },
  steps: { type: Array, default: () => [] },
  dashboards: { type: Array, default: () => [] },
})
const emit = defineEmits(['change'])

const EMOJIS = ['😀', '😃', '😄', '😁', '😆', '😊', '😍', '🤩', '😘', '😎', '🤔', '😮', '😢', '😭', '😡', '👍', '👏', '🙏', '💪', '🎉',
                '🔥', '✅', '❌', '⚠️', '📌', '📣', '⏰', '📅', '📈', '💡', '❤️', '⭐']

const title = ref(props.titleValue)
const buttons = ref([...(props.buttonsValue || [])])
const bodyRef = ref(null)
const focus = ref(false)
const emoji = reactive({ visible: false, x: 0, y: 0 })
const vars = reactive({ visible: false, x: 0, y: 0 })
let savedRange = null
let selfUpdate = false

function chipEl(seg) {
  const el = document.createElement('span')
  el.className = 'me-chip'
  el.contentEditable = 'false'
  el.dataset.var = JSON.stringify(seg.var)
  el.dataset.label = seg.label || ''
  el.innerHTML = `${escapeHtml(seg.label || '变量')}<span class="me-chip-x" data-x="1">✕</span>`
  return el
}
function escapeHtml(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]) }

function render(segs) {
  const el = bodyRef.value
  if (!el) return
  el.innerHTML = ''
  for (const seg of segs || []) {
    if (seg.t === 'var') el.appendChild(chipEl(seg))
    else if (seg.t === 'br') el.appendChild(document.createElement('br'))
    else el.appendChild(document.createTextNode(seg.v || ''))
  }
}

function parse() {
  const out = []
  const walk = (node, isRoot) => {
    for (const n of node.childNodes) {
      if (n.nodeType === 3) {
        if (n.textContent) out.push({ t: 'text', v: n.textContent })
      } else if (n.nodeType === 1) {
        if (n.dataset?.var) out.push({ t: 'var', var: JSON.parse(n.dataset.var), label: n.dataset.label })
        else if (n.tagName === 'BR') out.push({ t: 'br' })
        else {
          if ((n.tagName === 'DIV' || n.tagName === 'P') && out.length && isRoot) out.push({ t: 'br' })
          walk(n, false)
        }
      }
    }
  }
  if (bodyRef.value) walk(bodyRef.value, true)
  return out
}

function emitAll() {
  selfUpdate = true
  emit('change', { title: title.value, content: parse(), buttons: buttons.value })
  nextTick(() => { selfUpdate = false })
}

onMounted(() => render(props.content))
watch(() => props.content, (c) => { if (!selfUpdate) render(c) })
watch(() => props.titleValue, (t) => { if (!selfUpdate) title.value = t })

function saveRange() {
  const sel = window.getSelection()
  if (sel && sel.rangeCount && bodyRef.value?.contains(sel.anchorNode)) savedRange = sel.getRangeAt(0).cloneRange()
}
function onBlur() { focus.value = false; saveRange() }
function restoreRange() {
  const el = bodyRef.value
  el.focus()
  const sel = window.getSelection()
  sel.removeAllRanges()
  if (savedRange) sel.addRange(savedRange)
  else {
    const r = document.createRange()
    r.selectNodeContents(el)
    r.collapse(false)
    sel.addRange(r)
  }
  return sel
}
function insertNode(node) {
  const sel = restoreRange()
  const range = sel.getRangeAt(0)
  range.deleteContents()
  range.insertNode(node)
  range.setStartAfter(node)
  range.collapse(true)
  sel.removeAllRanges()
  sel.addRange(range)
  savedRange = range.cloneRange()
  emitAll()
}
function insertText(t) { insertNode(document.createTextNode(t)); emoji.visible = false }
function insertVar(v, label) {
  insertNode(chipEl({ var: v, label }))
  vars.visible = false
}
function onBodyClick(e) {
  if (e.target.dataset?.x) { e.target.parentElement.remove(); emitAll() }
}
function onKey(e) {
  if (e.key === 'Enter') {   // 统一换行为 <br>（避免浏览器插入 div 结构）
    e.preventDefault()
    saveRange()
    insertNode(document.createElement('br'))
  }
}
function toggleEmoji(e) {
  saveRange()
  const r = e.currentTarget.getBoundingClientRect()
  Object.assign(emoji, { visible: !emoji.visible, x: r.left, y: r.bottom + 6 })
}
function openVars(e) {
  saveRange()
  const r = e.currentTarget.getBoundingClientRect()
  Object.assign(vars, { visible: true, x: r.left, y: r.bottom + 6 })
}
function closeMenus() { emoji.visible = false; vars.visible = false }
function addButton() {
  if (buttons.value.length >= 1) return
  buttons.value.push({ label: '查看记录' })
  emitAll()
}
</script>

<style scoped>
.me { border: 1px solid var(--st-border); border-radius: 8px; padding: 14px 18px 6px; background: #fff; }
.me.focus { border-color: var(--st-primary); }
.me-title { width: 100%; border: none; outline: none; font-size: 18px; font-weight: 700; padding: 0 0 10px; color: var(--st-text-1); }
.me-body { min-height: 170px; outline: none; font-size: 15px; line-height: 2; color: var(--st-text-1); white-space: pre-wrap; word-break: break-word; }
.me-body:empty::before { content: attr(data-placeholder); color: var(--st-text-4); }
.me-body :deep(.me-chip) { display: inline-flex; align-items: center; gap: 4px; background: #F0F1F3; border-radius: 4px; padding: 0 6px; margin: 0 2px; line-height: 26px; font-size: 14px; user-select: none; }
.me-body :deep(.me-chip-x) { color: var(--st-text-3); cursor: pointer; font-size: 12px; }
.me-body :deep(.me-chip-x:hover) { color: var(--st-text-1); }
.me-buttons { padding: 6px 0; }
.me-btn-chip { display: inline-flex; gap: 6px; align-items: center; border: 1px solid var(--st-border); border-radius: 6px; padding: 4px 14px; font-size: 13px; color: var(--st-primary); }
.me-x { color: var(--st-text-3); cursor: pointer; }
.me-bar { display: flex; align-items: center; gap: 18px; border-top: 1px solid var(--st-border); margin-top: 8px; padding: 10px 0 6px; }
.me-tool { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; color: var(--st-text-2); cursor: pointer; }
.me-tool:hover { color: var(--st-text-1); }
.me-right { margin-left: auto; }
.me-mask { position: fixed; inset: 0; z-index: 3990; }
.me-emoji { position: fixed; z-index: 4000; background: #fff; border-radius: 10px; box-shadow: var(--st-shadow-pop); padding: 8px; display: grid; grid-template-columns: repeat(8, 32px); gap: 2px; }
.me-e { font-size: 20px; text-align: center; cursor: pointer; border-radius: 6px; line-height: 32px; }
.me-e:hover { background: var(--st-bg-hover); }
</style>
