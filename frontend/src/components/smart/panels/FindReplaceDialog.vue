<template>
  <!-- 查找替换（设计文档 §7.5）：非模态浮动卡片，查找定位 → 单个/全部替换 -->
  <el-dialog :model-value="visible" width="400px" :show-close="false" class="smart-find-dialog"
             append-to-body destroy-on-close :close-on-press-escape="false"
             v-bind="dialogAttrs" @update:model-value="onDialogModel" @opened="focusFindInput">
    <div class="fr-panel" @keydown.esc.stop.prevent="closePanel">
      <div class="fr-head" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="stopDrag" @pointercancel="stopDrag" @lostpointercapture="stopDrag">
        <span class="fr-title">{{ expanded ? '查找替换' : '查找' }}</span>
        <button class="st-button st-button--icon fr-close" type="button" aria-label="关闭" @click="closePanel">
          <StIcon name="close" :size="16" />
        </button>
      </div>

      <div class="fr-find-wrap">
        <input ref="findInputRef" v-model="find" class="st-control st-control--native fr-input fr-find-input"
               :class="{ 'has-nav': searched }" placeholder="输入查找内容"
               :readonly="busy" @input="onFindInput" @keydown.enter.prevent="onFindEnter" />
        <div v-if="searched" class="fr-nav" aria-label="查找结果导航">
          <button class="st-button st-button--icon " type="button" aria-label="上一个" :disabled="!matches.length || busy" @click="findPrev">
            <StIcon name="back" :size="14" />
          </button>
          <span class="fr-count">{{ currentIndex >= 0 ? currentIndex + 1 : 0 }}/{{ matches.length }}</span>
          <button class="st-button st-button--icon " type="button" aria-label="下一个" :disabled="!matches.length || busy" @click="findNext">
            <StIcon name="chevron-right" :size="14" />
          </button>
        </div>
      </div>

      <button v-if="!expanded" class="st-button fr-expand" type="button" @click="expanded = true">
        <span>替换</span><StIcon name="chevron-down" :size="13" />
      </button>

      <template v-if="expanded">
        <label class="fr-label" for="smart-find-replace">替换为</label>
        <input id="smart-find-replace" v-model="replace" class="st-control st-control--native fr-input" placeholder="输入替换内容"
               :disabled="busy" @input="status = ''" @keydown.enter.prevent="doReplaceCurrent" />
        <div class="fr-ops">
          <button class="st-button st-button--primary fr-btn fr-primary" type="button" :disabled="!find || busy" @click="doFind">查找</button>
          <div class="fr-replace-ops">
            <button class="st-button fr-btn" type="button" :disabled="!canReplace" @click="doReplaceCurrent">替换</button>
            <button class="st-button fr-btn" type="button" :disabled="!canReplace" @click="confirmVisible = true">全部替换</button>
          </div>
        </div>
      </template>

      <div v-if="status" class="fr-status" role="status">{{ status }}</div>
    </div>
  </el-dialog>

  <el-dialog v-model="confirmVisible" title="提示" width="360px" class="fr-confirm"
             append-to-body :close-on-click-modal="false">
    <div class="fr-confirm-text">
      确定将此智能表内的 {{ matches.length }} 处 “{{ find }}” 全部替换为 “{{ replace }}” 吗？
    </div>
    <template #footer>
      <div class="fr-confirm-ops">
        <button class="st-button st-button--primary fr-btn fr-primary" type="button" :disabled="busy" @click="doReplaceAll">确定</button>
        <button class="st-button fr-btn" type="button" :disabled="busy" @click="confirmVisible = false">取消</button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { smartSearchReplace } from '../../../api/index.js'
import { regOf } from '../../../smart/registry/fieldRegistry.js'
import { anchoredDialogAttrs } from '../../../smart/utils/anchorDialog.js'
import StIcon from '../icons/StIcon.vue'

const props = defineProps({
  visible: Boolean,
  tableId: Number,
  viewId: Number,
  at: { type: Object, default: null },
  orderMatches: { type: Function, default: null },
})
const emit = defineEmits(['close', 'replaced', 'highlight', 'locate'])

const dragPosition = ref(null)
let drag = null
const dialogAttrs = computed(() => {
  const attrs = anchoredDialogAttrs(props.at, 400, 380)
  if (dragPosition.value) attrs.style = {
    ...attrs.style, left: `${dragPosition.value.x}px`, top: `${dragPosition.value.y}px`,
    right: 'auto', maxHeight: `calc(100vh - ${dragPosition.value.y + 12}px)`,
  }
  return attrs
})

function startDrag(event) {
  if (event.button !== 0 || event.target.closest('button')) return
  const rect = event.currentTarget.closest('.el-dialog')?.getBoundingClientRect()
  if (!rect) return
  drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, rect }
  event.currentTarget.setPointerCapture(event.pointerId)
  event.preventDefault()
}

function moveDrag(event) {
  if (!drag || event.pointerId !== drag.pointerId) return
  const { rect, x, y } = drag
  dragPosition.value = {
    x: Math.max(12, Math.min(rect.left + event.clientX - x, window.innerWidth - rect.width - 12)),
    y: Math.max(12, Math.min(rect.top + event.clientY - y, window.innerHeight - rect.height - 12)),
  }
}

function stopDrag() { drag = null }
const findInputRef = ref(null)
const expanded = ref(false)
const find = ref('')
const replace = ref('')
const matches = ref([])
const currentIndex = ref(-1)
const searched = ref(false)
const status = ref('')
const busy = ref(false)
const confirmVisible = ref(false)
let requestSeq = 0

const currentMatch = computed(() => matches.value[currentIndex.value] || null)
const canReplace = computed(() => searched.value && matches.value.length > 0 && !busy.value)

function matchKey(m) {
  return m ? `${m.recordId}:${m.field}` : ''
}

function syncHighlight() {
  emit('highlight', { matches: matches.value, currentIndex: currentIndex.value })
}

function locateCurrent() {
  if (currentMatch.value) emit('locate', currentMatch.value)
}

function focusFindInput() {
  findInputRef.value?.focus()
}

function resetState() {
  requestSeq += 1
  dragPosition.value = null
  stopDrag()
  expanded.value = false
  find.value = ''
  replace.value = ''
  matches.value = []
  currentIndex.value = -1
  searched.value = false
  status.value = ''
  busy.value = false
  confirmVisible.value = false
  syncHighlight()
}

function closePanel() {
  if (!props.visible) return
  emit('close')
}

function onDialogModel(value) {
  if (!value) closePanel()
}

function onFindInput() {
  searched.value = false
  matches.value = []
  currentIndex.value = -1
  status.value = ''
  syncHighlight()
}

async function refreshMatches(seq, { preservePosition = false, message = null } = {}) {
  const oldIndex = currentIndex.value
  const oldKey = matchKey(currentMatch.value)
  const res = await smartSearchReplace(props.tableId, { find: find.value, ...(props.viewId ? { view_id: props.viewId } : {}) })
  if (seq !== requestSeq || !props.visible) return false

  const results = Array.isArray(res.matches) ? res.matches : []
  const nextMatches = props.orderMatches ? props.orderMatches(results) : results
  matches.value = nextMatches
  searched.value = true
  let nextIndex = nextMatches.length ? 0 : -1
  if (preservePosition && nextMatches.length) {
    const sameIndex = oldKey ? nextMatches.findIndex(m => matchKey(m) === oldKey) : -1
    nextIndex = sameIndex >= 0 ? sameIndex : Math.min(Math.max(oldIndex, 0), nextMatches.length - 1)
  }
  currentIndex.value = nextIndex
  status.value = message ?? (nextMatches.length ? '' : '未找到匹配内容')
  syncHighlight()
  locateCurrent()
  return true
}

function doFind() {
  if (searched.value && matches.value.length) return findNext()
  return refreshSearch()
}

async function refreshSearch() {
  if (!find.value || busy.value) return
  const seq = ++requestSeq
  busy.value = true
  status.value = ''
  try {
    await refreshMatches(seq)
  } catch (e) {
    if (seq === requestSeq) ElMessage.error(e?.response?.data?.detail || '查找失败')
  } finally {
    if (seq === requestSeq) busy.value = false
  }
}

function onFindEnter(e) {
  if (searched.value && matches.value.length) {
    if (e.shiftKey) findPrev()
    else findNext()
  } else {
    doFind()
  }
}

function goTo(index) {
  if (!matches.value.length || busy.value) return
  const total = matches.value.length
  currentIndex.value = ((index % total) + total) % total
  status.value = ''
  syncHighlight()
  locateCurrent()
}

function findNext() { goTo(currentIndex.value + 1) }
function findPrev() { goTo(currentIndex.value - 1) }

function blockedMessage(match) {
  if (match?.blockedReason === 'permission') return '你没有编辑该单元格的权限'
  const label = regOf({ field_type: match?.fieldType }).label
  return `无法替换 “${label}” 类型`
}

async function doReplaceCurrent() {
  if (!canReplace.value || !currentMatch.value) return
  const target = currentMatch.value
  if (!target.replaceable) {
    status.value = blockedMessage(target)
    return
  }
  const seq = ++requestSeq
  busy.value = true
  status.value = ''
  try {
    const res = await smartSearchReplace(props.tableId, {
      find: find.value, replace: replace.value, replace_current: true,
      record_id: target.recordId, field: target.field,
    })
    if (seq !== requestSeq || !props.visible) return
    const changes = Array.isArray(res.changes) ? res.changes : []
    if (changes.length) emit('replaced', { changes, label: '替换 1 处' })
    await refreshMatches(seq, { preservePosition: true })
  } catch (e) {
    if (seq === requestSeq) ElMessage.error(e?.response?.data?.detail || '替换失败')
  } finally {
    if (seq === requestSeq) busy.value = false
  }
}

async function doReplaceAll() {
  if (!canReplace.value) return
  confirmVisible.value = false
  const seq = ++requestSeq
  busy.value = true
  status.value = ''
  try {
    const res = await smartSearchReplace(props.tableId, {
      find: find.value, replace: replace.value, replace_all: true,
    })
    if (seq !== requestSeq || !props.visible) return
    const changes = Array.isArray(res.changes) ? res.changes : []
    const replacedCells = Number(res.replacedCells || 0)
    const skipped = Number(res.skipped || 0)
    if (changes.length) emit('replaced', { changes, label: `全部替换 ${replacedCells} 处` })
    const message = skipped ? '部分内容无法替换' : null
    if (!skipped && replacedCells) ElMessage.success(`已替换 ${replacedCells} 处`)
    await refreshMatches(seq, { preservePosition: true, message })
  } catch (e) {
    if (seq === requestSeq) ElMessage.error(e?.response?.data?.detail || '全部替换失败')
  } finally {
    if (seq === requestSeq) busy.value = false
  }
}

watch(() => props.visible, async open => {
  resetState()
  if (open) {
    await nextTick()
    focusFindInput()
  }
})

defineExpose({ refresh: refreshSearch })
</script>

<style scoped>
.fr-panel { display: flex; flex-direction: column; color: var(--st-text-2); }
.fr-head { cursor: move; touch-action: none; user-select: none; display: flex; align-items: center; justify-content: space-between; margin: 0 -20px 12px; padding: 12px 20px 0; }
.fr-title { font-size: var(--st-font-size); line-height: 26px; font-weight: 500; }
.fr-close { width: 28px; height: 28px; padding: 0; border: 0; background: transparent; color: var(--st-text-2); cursor: pointer; display: grid; place-items: center; }
.fr-close:hover { color: var(--st-text-2); }
.fr-find-wrap { position: relative; }
.fr-input { box-sizing: border-box; width: 100%; height: 40px; padding: 0 12px; border: 1px solid #D0D3D6; border-radius: 4px; background: #FFF; color: var(--st-text-2); font: inherit; font-size: var(--st-font-size); outline: none; }
.fr-input::placeholder { color: #A8ABB0; }
.fr-input:focus { border-color: var(--st-primary); }
.fr-input:disabled { background: #FFF; color: var(--st-text-2); }
.fr-find-input.has-nav { padding-right: 150px; }
.fr-nav { position: absolute; top: 50%; right: 11px; transform: translateY(-50%); display: flex; align-items: center; gap: 9px; padding-left: 8px; background: #FFF; color: var(--st-text-2); }
.fr-nav button { width: 16px; height: 24px; padding: 0; border: 0; background: transparent; color: inherit; cursor: pointer; display: grid; place-items: center; }
.fr-nav button:disabled { opacity: .4; cursor: not-allowed; }
.fr-count { min-width: 38px; color: var(--st-text-2); font-size: var(--st-font-size); text-align: center; }
.fr-expand { align-self: center; display: flex; align-items: center; gap: 4px; margin-top: 10px; padding: 0; border: 0; background: transparent; color: var(--st-text-2); font-size: var(--st-font-size); cursor: pointer; }
.fr-label { margin: 16px 0 8px; font-size: var(--st-font-size); line-height: 22px; }
.fr-ops { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 22px; }
.fr-replace-ops { display: flex; gap: 12px; }
.fr-btn { min-width: 88px; height: 36px; padding: 0 16px; border: 0; border-radius: 4px; background: #F2F3F3; color: var(--st-text-2); font-size: var(--st-font-size); cursor: pointer; white-space: nowrap; }
.fr-btn:hover:not(:disabled) { filter: brightness(.98); }
.fr-btn:disabled { opacity: .42; cursor: not-allowed; }
.fr-primary { background: var(--st-primary); color: #FFF; }
.fr-status { margin-top: 18px; color: var(--st-text-2); font-size: var(--st-font-size); line-height: 22px; }
.fr-confirm-text { color: var(--st-text-2); font-size: var(--st-font-size); line-height: 24px; word-break: keep-all; overflow-wrap: anywhere; }
.fr-confirm-ops { display: flex; gap: 16px; }
.fr-confirm-ops .fr-btn { flex: 1; }
</style>

<style>
.smart-find-dialog { padding: 0; position: fixed; margin: 0; max-width: calc(100vw - 24px); border-radius: 8px; box-shadow: 0 8px 30px rgba(31, 35, 41, .14); }
.smart-find-dialog:not(.st-at-dialog) { top: 148px; right: 16px; }
.smart-find-dialog.st-at-dialog { right: auto; }
.smart-find-dialog .el-dialog__header { display: none; }
.smart-find-dialog .el-dialog__body { padding: 0 20px 12px; }
.fr-confirm { border-radius: 10px; }
.fr-confirm .el-dialog__header { padding: 20px 24px 12px; }
.fr-confirm .el-dialog__title { color: var(--st-text-1); font-size: var(--st-font-size-title); font-weight: 600; }
.fr-confirm .el-dialog__body { padding: 0 24px 20px; }
.fr-confirm .el-dialog__footer { padding: 0 24px 20px; }
@media (max-width: 520px) {
  .smart-find-dialog { right: 12px; }
  .smart-find-dialog .el-dialog__body { padding-right: 20px; padding-left: 20px; }
}
</style>
