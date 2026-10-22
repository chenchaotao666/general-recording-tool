<template>
  <!-- 编辑态挂载器：按字段类型分发编辑器（设计文档 §4：六类提交策略）。
       统一契约：props {field, record}，emit commit(value) / cancel() -->
  <!-- 内联输入（数字/百分数/货币）：失焦/回车提交，Esc 取消 -->
  <el-input
    v-if="!preview && editorKind === 'inline' && ft !== 'text'" ref="inputRef" v-model="draft" size="small" class="cell-editor numeric-input" :class="{ 'percent-input': ft === 'percent' }"
    @blur="commitInline" @keydown.enter="enterInline" @keydown.tab="tabInline" @keyup.esc="$emit('cancel')">
    <template v-if="ft === 'percent'" #suffix><span class="numeric-suffix">%</span></template>
  </el-input>

  <!-- 文本：双击进入的浮层编辑（企微式）。边界=单元格（边框与选中态同款 2px 主色），
       内容多时自动增高（上限 220px 后滚动）；Enter 提交后向下，Shift+Enter/Alt+Enter 换行。
       preview（单击选中态）：同一浮层只读展示全文——用 div 而非 readonly textarea
       （Chrome 里 readonly textarea 的内容仍可被拖选），失焦/点外部/Esc 关闭，双击浮层进编辑 -->
  <template v-else-if="preview || editorKind === 'inline'">
    <span ref="anchorRef" class="cell-anchor" />
    <teleport to="body">
      <div v-if="overlayRect" v-show="!overlayOut" class="cell-overlay" :class="{ preview }" :style="overlayStyle"
           @mousedown.stop="onPreviewMouseDown" @click="onPreviewClick" @dblclick.stop="preview && $emit('enter-edit')">
        <template v-if="preview">
          <div ref="taRef" class="cell-textarea preview-text" :style="taStyle">{{ draft }}</div>
          <span v-if="fillHandle" class="text-fill-handle" @pointerdown.stop="startFill" @click.stop @dblclick.stop />
        </template>
        <textarea v-else ref="taRef" v-model="draft" class="cell-textarea" :style="taStyle" rows="1"
                  @input="autoGrow" @keydown.esc="discard"
                  @keydown.enter="enterInline" @keydown.tab="tabInline" @blur="commitInline" />
      </div>
    </teleport>
  </template>

  <!-- 单选/多选：自定义下拉面板（设计稿：单元格输入-单选.png；搜索/创建选项/联动过滤） -->
  <SelectCellPanel
    v-else-if="editorKind === 'select'" :field="field" :record="record" :frozen="frozen" :initial-query="initialInput" :advance-on-enter="advanceOnEnter" @advance="direction => $emit('advance', direction)"
    @commit="(v) => $emit('commit', v)" @cancel="$emit('cancel')"
    @commit-soft="(v) => $emit('commit-soft', v)" @collapse="$emit('collapse')"
    @add-option="(label) => $emit('add-option', label)" />

  <!-- 日期（面板挂 body：teleported=false 会被单元格 overflow 裁掉，等于打不开） -->
  <div v-else-if="editorKind === 'date'" class="cell-date-wrap" @keydown.enter.capture="markDateEnter" @keyup.enter="finishDateEnter" @keydown.tab.capture="tabDate">
  <el-date-picker
    ref="dateRef" v-model="draft" size="small" class="cell-editor cell-date-editor"
    :type="cfg.includeTime ? 'datetime' : 'date'" value-format="YYYY-MM-DD HH:mm:ss"
    :format="dateDisplayFormat" :prefix-icon="NoIcon"
    @change="commit" @visible-change="(vis) => !vis && $emit('cancel')" />
  </div>

  <PeoplePicker v-else-if="editorKind === 'member'" ref="selectRef" :model-value="draft" class="cell-editor" grid-cell
    :multiple="cfg.multiple !== false" :people="memberList" :initial-query="initialInput" :advance-on-enter="advanceOnEnter" @advance="direction => $emit('advance', direction)" @confirm="v => $emit('commit', v)"
    @cancel="$emit('cancel')" @people-loaded="rememberPeople" />

  <LinkCellPanel v-else-if="editorKind === 'url'" ref="selectRef" :value="draft || null" selected :advance-on-enter="advanceOnEnter" @advance="direction => $emit('advance', direction)"
    @commit="v => $emit('commit', v)" @cancel="$emit('cancel')" @collapse="$emit('cancel')" />

  <!-- 进度：百分比格式输入百分数，保存时换算回原始范围值。 -->
  <el-input v-else-if="editorKind === 'progress'" ref="inputRef" v-model="draft" size="small" class="cell-editor numeric-input progress-input" :class="{ 'percent-input': progressPercent }"
            inputmode="decimal" @blur="commitInline" @keydown.enter="enterInline" @keydown.tab="tabInline" @keydown.esc="discard">
    <template v-if="progressPercent" #suffix><span class="numeric-suffix">%</span></template>
  </el-input>

  <ImageCellPanel v-else-if="ft === 'image'" ref="selectRef" :value="draft" @commit="v => { draft = v; $emit('commit-soft', v) }" @cancel="$emit('cancel')" @collapse="$emit('collapse')" />
  <FileCellPanel v-else-if="ft === 'file'" ref="selectRef" :value="Array.isArray(draft) ? draft : []" selected
    @commit="v => { draft = v; $emit('commit-soft', v) }" @cancel="$emit('cancel')" @collapse="$emit('cancel')" />

  <!-- 关联：目标表记录选择（面板挂 body 防单元格裁剪） -->
  <RelationCellPanel v-else-if="editorKind === 'relation'" ref="selectRef" :field="field" :record="record" :value="draft" selected
    @commit="v => { draft = v; $emit('commit-soft', v) }" @cancel="$emit('cancel')" @collapse="$emit('cancel')" />

  <!-- 只读字段：提示气泡（BlockedEditor，设计文档 §4.3） -->
  <div v-else class="blocked" @click.stop>
    <span class="blocked-text">{{ blockedText }}</span>
    <el-button link type="primary" size="small" @click="$emit('open-config', field)">修改设置</el-button>
  </div>
</template>

<script setup>
import { useGridScrollCollapse } from '../../../smart/utils/useGridScrollCollapse.js'
import { computed, getCurrentInstance, h, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, dayjs } from 'element-plus'
import { regOf } from '../../../smart/registry/fieldRegistry.js'
import { dayjsDateFormat } from '../../../smart/utils/format.js'
import SelectCellPanel from './SelectCellPanel.vue'
import PeoplePicker from '../../people/PeoplePicker.vue'
import ImageCellPanel from './ImageCellPanel.vue'
import FileCellPanel from './FileCellPanel.vue'
import LinkCellPanel from './LinkCellPanel.vue'
import RelationCellPanel from './RelationCellPanel.vue'
import { afterFrame, isDisplayCell, visibleCellRect } from '../../../smart/utils/vxeCell.js'

const props = defineProps({
  advanceOnEnter: Boolean,
  initialInput: { type: String, default: undefined },
  field: { type: Object, required: true },
  record: { type: Object, required: true },
  frozen: { type: Boolean, default: false },   // 列是否被冻结（判断显示副本在哪个 wrapper）
  preview: { type: Boolean, default: false },  // 单击选中的只读预览（仅文本浮层用）
  fillHandle: Boolean,
})
const emit = defineEmits(['advance', 'commit', 'commit-soft', 'cancel', 'open-config', 'add-option', 'enter-edit', 'collapse', 'fill-start'])

const memberList = inject('smartMembers', { value: [] })          // [{id, name}]
function rememberPeople(people) {
  const merged = new Map((memberList.value || []).map(p => [p.id, p]))
  people.forEach(p => merged.set(p.id, p))
  memberList.value = [...merged.values()]
}

const cfg = computed(() => props.field.options || {})
// 日期编辑框的显示格式与查看态 formatDate 一致（字段格式 yyyy… → dayjs 格式），双击进编辑文字不变
const dateDisplayFormat = computed(() => dayjsDateFormat(cfg.value))
const NoIcon = { render: () => h('span') }   // 去掉日期框前置日历图标：文字起点与查看态一致
const ft = computed(() => props.field.field_type || 'text')
const editorKind = computed(() => regOf(props.field).editor)
const isMulti = computed(() => ft.value === 'multiSelect')
const progressPercent = computed(() => ft.value === 'progress' && cfg.value.numberFormat === 'percent')
const progressMin = computed(() => Number(cfg.value.range?.min ?? 0))
const progressMax = computed(() => Math.max(progressMin.value + 1, Number(cfg.value.range?.max ?? 100)))
const blockedText = computed(() => ({
  formula: '公式计算结果不可直接编辑', lookup: '查找引用内容不可直接编辑',
  createdBy: '创建人字段不可直接编辑', lastModifiedBy: '最后编辑人字段不可直接编辑',
  createdTime: '创建时间字段不可直接编辑', lastModifiedTime: '最后编辑时间字段不可直接编辑',
  autoNumber: '自动编号不可直接编辑',
}[ft.value] || '该字段不可直接编辑'))

const cur = props.record[props.field.field_name]
const draft = ref(
  Array.isArray(cur) ? [...cur]
    // 多选兜底包成数组（单选改多选后存量值仍是标量 id）
    : isMulti.value ? (cur == null || cur === '' ? [] : [cur])
    : (cur ?? ''))
if (progressPercent.value && cur != null && cur !== '') {
  draft.value = +(((Number(cur) - progressMin.value) / (progressMax.value - progressMin.value)) * 100).toFixed(10)
}


watch(() => props.initialInput, value => {
  if (value != null && ['inline', 'progress'].includes(editorKind.value)) draft.value = value
}, { immediate: true })
const inputRef = ref(null)
const selectRef = ref(null)
const dateRef = ref(null)
const selfInst = getCurrentInstance()   // 必须在 setup 顶层捕获，回调里调用会返回 null

// 文本浮层编辑：定位锚=单元格 rect；高度随内容增长（上限 220px 滚动）
const anchorRef = ref(null)
const taRef = ref(null)
const overlayRect = ref(null)
const textFont = ref({})
function startFill(event) {
  if (event.button !== 0) return
  const td = anchorRef.value?.closest('td')
  const rect = event.currentTarget.closest('.cell-overlay').getBoundingClientRect()
  if (td) emit('fill-start', event, td, rect)
}
const overlayStyle = computed(() => {
  const r = overlayRect.value
  if (!r) return {}
  // 宽度严格=单元格宽（只纵向随内容增高）
  return {
    left: `${r.left}px`, top: `${r.top}px`,
    width: `${r.width}px`, minHeight: `${r.height}px`,
    ...textFont.value,
  }
})
// 与查看态的首行行框对齐；扣除浮层的 2px 边框后计算输入框内边距。
const taStyle = computed(() => {
  const r = overlayRect.value
  // 默认行高居中时行框偏移 6px；高行顶对齐时为上内边距 7px - 光学上移 2px。
  const viewTop = (r?.height || 36) > 36 ? 5 : 6
  const padTop = Math.max(0, viewTop - 2)
  // 底部留白封顶 6px：内容盒最小高度由 autoGrow 的 min（= 单元格高）兜住；若按行高补齐底部留白，
  // 行高变大时多行文本会把浮层撑出单元格（内容明明放得下，参照 PixPin_2026-10-17_16-53-48）
  const padBottom = Math.min(6, ((r?.height || 36) - 26) - padTop)
  return { padding: `${padTop}px 6px ${padBottom}px` }
})
function autoGrow() {
  const ta = taRef.value
  if (!ta) return
  ta.style.height = 'auto'
  // border-box：scrollHeight 即整高（含 padding）；内容盒至少与单元格等高（减去浮层边框 4px）
  const min = (overlayRect.value?.height || 36) - 4
  const need = ta.scrollHeight
  // 单行吸附到内容盒等高（容忍 scrollHeight 的 1px 取整误差）；多行按内容撑高（上限 216px）
  const h = need <= min + 1 ? min : Math.min(need, 216)
  ta.style.height = `${h}px`
  ta.style.overflowY = need > h ? 'auto' : 'hidden'
}
function focusTextarea() {
  const ta = taRef.value
  if (!ta || props.preview) return
  ta.focus({ preventScroll: true })
  const end = draft.value?.length || 0
  ta.setSelectionRange?.(end, end)
}
onMounted(async () => {
  // vxe 冻结列会把同一单元格渲染多份；非显示副本的编辑器必须完全惰性（不聚焦不开浮层），
  // 否则多实例互抢焦点、浮层定位到隐藏副本（冻结列单击/双击看不到内容的原因）。
  // 等一帧（vxe 后置补 fixed--hidden）再按实际可见性判定；
  // 多根组件的 $el 可能是文本锚点节点，没有 closest，须先取到元素节点
  await nextTick()
  await afterFrame()
  if (discarded) return   // 等待期间已卸载
  const root = selfInst?.proxy?.$el
  const rootEl = root?.nodeType === 1 ? root : root?.parentElement
  const hostTd = rootEl?.closest?.('td')
  if (hostTd && !isDisplayCell(hostTd)) return
  const el = inputRef.value?.focus?.() || selectRef.value?.focus?.() || dateRef.value?.focus?.()
  // 键入进入时由 initialInput 提供新值；显式打开编辑器时保留原值。
  const nativeInput = inputRef.value?.input || inputRef.value?.$el?.querySelector?.('input') || rootEl?.querySelector?.('.cell-date-editor input')
  if (nativeInput && editorKind.value === 'date' && props.initialInput != null) {
    nativeInput.value = props.initialInput
    nativeInput.dispatchEvent(new Event('input', { bubbles: true }))
  }
  if (nativeInput) nativeInput.setSelectionRange?.(nativeInput.value.length, nativeInput.value.length)
  // 文本浮层：锚定单元格位置；编辑态聚焦，预览态（div）不可聚焦、由 Esc/点外部关闭
  if (anchorRef.value) {
    const td = anchorRef.value.closest('td') || anchorRef.value.parentElement
    overlayRect.value = td?.getBoundingClientRect() || null
    // 浮层挂到 body 后不再继承表格字体，显式保留宿主字体，避免字形和基线跳动。
    if (td) {
      const style = getComputedStyle(td)
      textFont.value = { fontFamily: style.fontFamily, color: style.color }
    }
    // 表格滚动时浮层跟随单元格；单元格滚出可视区（或被表头/统计行遮住）时隐藏
    document.addEventListener('scroll', onAnyScroll, true)
    window.addEventListener('resize', onAnyScroll)
    // overlayRect 驱动 v-if 渲染内容——等下一拍渲染完成再聚焦（否则 taRef 还是 null）
    nextTick(() => {
      autoGrow()
      if (props.preview) {
        // 预览态：点击浮层和宿主单元格之外 = 关闭（div 无焦点，没有 blur 可用）
        document.addEventListener('mousedown', onPreviewOutside, true)
        return
      }
      focusTextarea()
      // 兜底：个别时序下焦点会被表格内部处理夺回，下一帧校验补焦
      requestAnimationFrame(() => {
        const ta = taRef.value
        if (ta && document.activeElement !== ta && document.body.contains(ta)) focusTextarea()
      })
    })
  }
  return el
})

// 浮层跟随：fixed 定位在打开时取的单元格坐标，滚动后需按单元格当前位置重算
const overlayOut = ref(false)
let scrollRaf = 0
function onAnyScroll(e) {
  if (e?.target && taRef.value && e.target === taRef.value) return   // 浮层自身内容滚动
  cancelAnimationFrame(scrollRaf)
  scrollRaf = requestAnimationFrame(() => {
    const td = anchorRef.value?.closest('td') || anchorRef.value?.parentElement   // 详情面板内：宿主是值容器
    const r = visibleCellRect(td)
    overlayOut.value = !r
    if (r && overlayRect.value) {
      overlayRect.value = { left: r.left, top: r.top, width: r.width, height: overlayRect.value.height }
    }
  })
}

// 预览态点外部关闭（捕获阶段；浮层自身 mousedown.stop 不会触发）
function onPreviewOutside(e) {
  const overlay = taRef.value?.closest('.cell-overlay')
  const td = anchorRef.value?.closest('td')
  if (overlay?.contains(e.target) || td?.contains(e.target)) return
  emit('cancel')
}

// 预览浮层自检测双击：原生 dblclick 在单元格 DOM 被选中态替换后可能不合成
// （两次点击落在不同元素上），原生计数与 500ms 跨元素补偿共同识别第二击
let lastPreviewClick = props.preview ? Date.now() : 0
function onPreviewMouseDown(event) {
  if (!props.preview || event.button !== 0 || event.target.closest('.text-fill-handle')) return
  // Recognize the second press before DOM replacement can swallow its click.
  // Native click counts respect the user's double-click speed preference.
  if (event.detail >= 2 || Date.now() - lastPreviewClick < 500) {
    event.preventDefault()
    emit('enter-edit')
  }
}
function onPreviewClick(event) {
  if (!props.preview) return
  const now = Date.now()
  if (event.detail >= 2 || now - lastPreviewClick < 500) emit('enter-edit')
  lastPreviewClick = now
}

// 预览 → 编辑切换：内容从 div 换成 textarea，补焦一次；预览的外部点击监听摘掉
// （否则编辑态点外部会被误取消，编辑态的关闭走 textarea blur 提交）
watch(() => props.preview, async (p) => {
  lastPreviewClick = p ? Date.now() : 0
  document.removeEventListener('mousedown', onPreviewOutside, true)
  if (!anchorRef.value) return
  await nextTick()
  if (discarded || !overlayRect.value) return
  autoGrow()
  if (p) document.addEventListener('mousedown', onPreviewOutside, true)
  else focusTextarea()
})

function enterInline(event) {
  if (event.isComposing || event.keyCode === 229) return
  if (ft.value === 'text' && (!props.advanceOnEnter || event.shiftKey || event.altKey) && !event.ctrlKey) {
    event.stopPropagation()
    return // Keep the textarea's native newline insertion.
  }
  event.preventDefault(); event.stopPropagation()
  commitInline(props.advanceOnEnter ? (event.shiftKey ? 'up' : 'down') : false)
}
function tabInline(event) {
  if (!props.advanceOnEnter || event.isComposing || event.keyCode === 229) return
  event.preventDefault(); event.stopPropagation()
  commitInline(event.shiftKey ? 'left' : 'right')
}
function commitInline(advance = false) {
  if (discarded) return
  // vxe 重渲染会直接重建单元格 DOM（不走 Vue 卸载），textarea 被移除文档树触发 blur，
  // 这种"卸载性 blur"不是用户操作，不提交
  if (taRef.value && !taRef.value.isConnected) return
  if (inputRef.value?.$el && !inputRef.value.$el.isConnected) return
  let v = draft.value
  if (['number', 'percent', 'currency', 'progress'].includes(ft.value)) {
    if (v === '' || v == null) v = null
    else if (Number.isNaN(Number(v))) { ElMessage.warning('请输入数字'); return }
    else v = Number(v)
    if (ft.value === 'progress' && v != null) {
      if (!Number.isFinite(v)) { ElMessage.warning('请输入有效数字'); return }
      if (progressPercent.value) v = progressMin.value + v / 100 * (progressMax.value - progressMin.value)
      v = Math.min(progressMax.value, Math.max(progressMin.value, v))
    }
  }
  discarded = true
  emit('commit', v === '' ? null : v)
  if (typeof advance === 'string') emit('advance', advance)
}
let dateEnter = false
function markDateEnter(event) { dateEnter = props.advanceOnEnter && !event.isComposing && event.keyCode !== 229 ? (event.shiftKey ? 'up' : 'down') : false }
function tabDate(event) {
  if (!props.advanceOnEnter || event.isComposing || event.keyCode === 229) return
  event.preventDefault(); event.stopPropagation()
  const raw = event.target.value?.trim() || ''
  const parsed = raw ? dayjs(raw, dateDisplayFormat.value, true) : null
  if (parsed && !parsed.isValid()) { ElMessage.warning('请输入有效日期'); return }
  draft.value = parsed ? parsed.format('YYYY-MM-DD HH:mm:ss') : null
  dateEnter = event.shiftKey ? 'left' : 'right'
  commit()
}
function finishDateEnter() { if (dateEnter && !discarded) commit() }
function commit() {
  if (discarded) return
  discarded = true
  emit('commit', draft.value === '' ? null : draft.value)
  if (dateEnter) { const direction = dateEnter; dateEnter = false; emit('advance', direction) }
}
function discard() {
  discarded = true
  emit('cancel')
}

// Esc/取消时浮层卸载会触发 blur → 防误提交：取消置标志，提交跳过
let discarded = false
useGridScrollCollapse(() => props.preview || ['inline', 'progress', 'date', 'member'].includes(editorKind.value), () => {
  if (props.preview) emit('collapse')
  else if (editorKind.value === 'inline' || editorKind.value === 'progress') commitInline()
  else if (editorKind.value === 'member') { selectRef.value?.collapse?.(); emit('collapse') }
  else emit('collapse')
})
// 组件被卸载（如 vxe 重渲染重建单元格 DOM）时 textarea 的 blur 会误触发提交，一律禁止
onBeforeUnmount(() => {
  discarded = true
  document.removeEventListener('mousedown', onPreviewOutside, true)
  document.removeEventListener('scroll', onAnyScroll, true)
  window.removeEventListener('resize', onAnyScroll)
  cancelAnimationFrame(scrollRaf)
})

</script>

<style scoped>
.cell-date-wrap { width: 100%; height: 100%; }
.cell-editor { width: 100%; height: 100%; }
.relation-editor :deep(.el-select__caret) { width: 24px; height: 24px; transform: none; }
.progress-input :deep(.el-input__inner) { font-variant-numeric: tabular-nums; }
/* 编辑态边框统一由 SmartGrid 画在 .vxe-cell 上，wrapper 自身不再描边（避免 EP content-box 高 2px 被裁） */
.cell-editor :deep(.el-input__wrapper) { height: 100%; box-shadow: none; }
/* 数值编辑与查看态共用字号和右侧留白，避免 small 输入框默认左对齐、12px 字号造成跳动。 */
.numeric-input :deep(.el-input__wrapper) { padding: 0 8px; }
.numeric-input :deep(.el-input__inner) {
  text-align: right; font-size: var(--st-font-size); font-family: inherit;
  color: var(--el-text-color-primary); transform: translateY(-2px);
}
.numeric-input :deep(.el-input__suffix) { font-size: var(--st-font-size); font-family: inherit; color: var(--el-text-color-primary); transform: translateY(-1px); }
.numeric-suffix { line-height: 22px; color: var(--st-text-3, #8f959e); }
.numeric-input :deep(.el-input__suffix-inner > :first-child) { margin-left: 0; }
.cell-anchor { display: block; width: 100%; height: 100%; }
/* 文本浮层编辑（teleport 到 body）：边框与选中态同款 2px 主色，边界起于单元格 */
.cell-overlay {
  position: fixed; z-index: 3000; background: #fff; box-sizing: border-box;
  border: 2px solid var(--st-primary); border-radius: 2px;   /* teleport 到 body，不在 EP 主色作用域内，直接用令牌 */
  box-shadow: 0 4px 16px rgba(0, 0, 0, .12);
}
.cell-textarea {
  display: block; width: 100%; border: none; outline: none; resize: none;
  box-sizing: border-box; padding: 5px 6px; overflow-y: hidden;
  font-family: inherit; font-size: var(--st-font-size); line-height: 22px; max-height: 216px;
}
/* 单击预览态：div 展示全文（Chrome 里 readonly textarea 仍可拖选，div 才可靠禁选） */
.cell-overlay.preview .preview-text {
  user-select: none; cursor: default; white-space: pre-wrap; word-break: break-all;
}
.text-fill-handle {
  position: absolute; right: -2px; bottom: -2px; width: 6px; height: 6px;
  background: var(--st-primary); border: 1px solid white; box-sizing: border-box;
  cursor: crosshair; touch-action: none;
}
.slider { padding: 0 8px; }
.url-editor { background: #fff; border: 1px solid var(--el-border-color); border-radius: 6px; padding: 8px; box-shadow: var(--el-box-shadow-light); min-width: 220px; }
.url-field { margin-bottom: 6px; }
.url-ops { display: flex; justify-content: flex-end; gap: 6px; }
.blocked { display: flex; align-items: center; gap: 6px; background: #fff; padding: 4px 8px; border-radius: 6px; box-shadow: var(--el-box-shadow-light); font-size: var(--st-font-size); }
.blocked-text { color: var(--el-text-color-secondary); }
.hint { color: var(--st-text-2); font-size: var(--st-font-size); margin-top: 4px; }
</style>

<style>
/* 日期编辑框：去前置图标，字号/字体/左边距与查看态单元格一致（双击进编辑文字不跳）。
   不能写在 scoped 里：el-date-picker 根元素不带本组件作用域属性，:deep 选择器命中不到 */
.cell-date-editor .el-input__prefix { display: none; }
.cell-date-editor .el-input__wrapper { padding: 0 8px; }
.cell-date-editor .el-input__inner { font-size: var(--st-font-size); font-family: inherit; color: var(--el-text-color-primary); }
</style>
