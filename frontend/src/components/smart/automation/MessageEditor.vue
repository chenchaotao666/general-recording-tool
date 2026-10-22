<template>
  <!-- 消息内容编辑器（§11.2）：标题（加粗）+ 正文富文本，变量为可单独删除的原子胶囊；
       底栏：添加表情 / 插入变量 / ＋ 添加按钮（对齐参照 右上角工具栏-新建自动化提醒.png） -->
  <div class="me" :class="{ focus }">
    <input v-model="title" class="me-title" placeholder="消息标题" @input="emitAll" />
    <div ref="bodyRef" class="me-body" contenteditable="true" data-placeholder="请输入消息内容，可插入变量"
         @input="emitAll" @focus="focus = true" @blur="onBlur" @keydown="onKey" @click="onBodyClick" />
    <div class="me-bar">
      <span class="me-tool" @mousedown.prevent @click="toggleEmoji($event)"><StIcon name="emoji" :size="16" />添加表情</span>
      <span class="me-tool" @mousedown.prevent @click="openVars($event)">{x} 插入变量</span>
      <el-popover v-model:visible="buttonOpen" :trigger="[]" :trigger-keys="[]" placement="bottom-end" :width="480" :hide-after="0" :show-arrow="false"
                  :popper-style="{ maxWidth: 'calc(100vw - 24px)' }">
        <template #reference><button type="button" class="me-tool me-right me-add-button" :disabled="buttons.length >= 2" @click="startButton()"><StIcon name="plus" :size="15" />添加按钮</button></template>
        <div class="me-button-form">
          <label>按钮标题</label><el-input v-model="buttonDraft.label" maxlength="20" placeholder="输入文本" />
          <label>按钮链接</label>
          <div class="me-link-input">
            <el-input v-if="!buttonDraft.variable" v-model="buttonDraft.url" placeholder="粘贴链接" />
            <button v-else type="button" class="me-link-chip" @click="buttonDraft.variable = null">{{ buttonDraft.variableLabel }} ×</button>
            <el-popover v-model:visible="linkVarsOpen" trigger="click" placement="bottom-end" :width="232" :teleported="false"
                        :popper-options="{ strategy: 'fixed' }" :hide-after="0" :show-arrow="false">
              <template #reference><button type="button" class="me-var-link">{x}</button></template>
              <VarMenu v-if="linkVarsOpen" inline hide-time :steps="linkSteps" :dashboards="dashboards" :reports="reports" @pick="pickButtonLink" />
            </el-popover>
          </div>
          <div class="me-button-actions"><el-button @click="buttonOpen = false">取消</el-button><el-button type="primary" :disabled="!buttonValid" @click="confirmButton">确定</el-button></div>
        </div>
      </el-popover>
    </div>
    <div v-if="buttons.length" class="me-buttons">
      <div v-for="(b, i) in buttons" :key="i" class="me-btn-chip">
        <span>{{ b.label }}</span>
        <el-dropdown trigger="click" :hide-after="0" @command="cmd => cmd === 'edit' ? startButton(i) : removeButton(i)">
          <button type="button" class="me-button-more" aria-label="按钮操作"><StIcon name="more-h" :size="16" /></button>
          <template #dropdown><el-dropdown-menu><el-dropdown-item command="edit">编辑</el-dropdown-item><el-dropdown-item command="delete">删除</el-dropdown-item></el-dropdown-menu></template>
        </el-dropdown>
      </div>
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
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import VarMenu from './VarMenu.vue'
import { listReports } from '../../../api/index.js'

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
const buttonOpen = ref(false)
const reports = ref([])
async function loadReports() {
  try { reports.value = await listReports() } catch { reports.value = [] }
}
const linkVarsOpen = ref(false)
const editIndex = ref(-1)
const buttonDraft = reactive({ label: '', url: '', variable: null, variableLabel: '' })
const safeUrl = value => /^https?:\/\/[^\s]+$/i.test(value) || /^\/(?!\/)[^\s\\]*$/.test(value)
const buttonValid = computed(() => buttonDraft.label.trim() && (buttonDraft.variable || safeUrl(buttonDraft.url.trim())))
const linkSteps = computed(() => props.steps.map(s => ({ ...s, vars: [
  ...(!['定时触发'].includes(s.name) ? [{ key: 'recordLink', label: '记录链接', icon: 'url', var: { kind: 'step', step: s.step, key: 'recordLink' } }] : []),
  ...(s.vars || []).filter(v => v.icon === 'url'),
] })))
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
watch(() => props.buttonsValue, value => { if (!selfUpdate) buttons.value = [...(value || [])] })

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
function startButton(index = -1) {
  if (index < 0 && buttons.value.length >= 2) return
  editIndex.value = index
  const b = buttons.value[index]
  Object.assign(buttonDraft, { label: b?.label || '', url: b?.link?.value || '', variable: b?.link?.var || null, variableLabel: b?.link?.label || '' })
  linkVarsOpen.value = false
  buttonOpen.value = true
  loadReports()
}
function pickButtonLink(variable, label) {
  Object.assign(buttonDraft, { variable, variableLabel: label })
  linkVarsOpen.value = false
}
function confirmButton() {
  if (!buttonValid.value) return
  const b = { label: buttonDraft.label.trim(), link: buttonDraft.variable
    ? { type: 'var', var: buttonDraft.variable, label: buttonDraft.variableLabel }
    : { type: 'static', value: buttonDraft.url.trim() } }
  if (editIndex.value < 0) buttons.value.push(b)
  else buttons.value.splice(editIndex.value, 1, b)
  buttonOpen.value = false
  emitAll()
}
function removeButton(index) { buttons.value.splice(index, 1); emitAll() }
</script>

<style scoped>
.me { min-width: 0; max-width: 100%; box-sizing: border-box; border: 1px solid var(--st-border); border-radius: 8px; padding: 14px 18px 6px; background: #fff; }
.me.focus { border-color: var(--st-primary); }
.me-title { width: 100%; border: none; outline: none; font-size: var(--st-font-size-title); font-weight: 700; padding: 0 0 10px; color: var(--st-text-1); }
.me-body { min-height: 170px; outline: none; font-size: var(--st-font-size); line-height: 2; color: var(--st-text-2); white-space: pre-wrap; word-break: break-word; }
.me-body:empty::before { content: attr(data-placeholder); color: var(--st-text-4); }
.me-body :deep(.me-chip) { display: inline-flex; align-items: center; gap: 4px; background: #F0F1F3; border-radius: 4px; padding: 0 6px; margin: 0 2px; line-height: 26px; font-size: var(--st-font-size); user-select: none; }
.me-body :deep(.me-chip-x) { color: var(--st-text-3); cursor: pointer; font-size: var(--st-font-size); }
.me-body :deep(.me-chip-x:hover) { color: var(--st-text-2); }
.me-buttons { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); min-width: 0; max-width: 100%; gap: 10px; padding: 6px 0; }
.me-btn-chip { display: flex; flex: 1; min-width: 0; align-items: center; background: #f2f3f5; border-radius: 5px; padding: 8px; font-size: var(--st-font-size); color: var(--st-text-2); }
.me-btn-chip > span { flex: 1; min-width: 0; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.me-btn-chip :deep(.el-dropdown) { flex: none; }
.me-button-more, .me-var-link { border: 0; background: transparent; color: var(--st-text-3); cursor: pointer; }
.me-add-button { border: 0; background: transparent; padding: 6px; }
.me-add-button:disabled { opacity: .4; cursor: not-allowed; }
.me-button-form { display: grid; grid-template-columns: 80px minmax(0, 1fr); gap: 14px; align-items: center; padding: 16px; }
.me-link-input { display: flex; align-items: center; gap: 4px; min-width: 0; }
.me-link-chip { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 8px; border: 0; background: #f2f3f5; cursor: pointer; }
.me-button-actions { grid-column: 1 / -1; display: flex; gap: 12px; margin-top: 10px; }
.me-button-actions > button { flex: 1; margin: 0; }
.me-x { color: var(--st-text-3); cursor: pointer; }
.me-bar { display: flex; align-items: center; gap: 18px; border-top: 1px solid var(--st-border); margin-top: 8px; padding: 10px 0 6px; }
.me-tool { display: inline-flex; align-items: center; gap: 6px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.me-tool:hover { color: var(--st-text-2); }
.me-right { margin-left: auto; }
.me-mask { position: fixed; inset: 0; z-index: 3990; }
.me-emoji { position: fixed; z-index: 4000; background: #fff; border-radius: 10px; box-shadow: var(--st-shadow-pop); padding: 8px; display: grid; grid-template-columns: repeat(8, 32px); gap: 2px; }
.me-e { font-size: var(--st-font-size); text-align: center; cursor: pointer; border-radius: 6px; line-height: 32px; }
.me-e:hover { background: var(--st-bg-hover); }
</style>
