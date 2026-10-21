<template>
  <div class="rd-content">
    <div v-if="record" class="rd-card">
      <div class="rd-head">
        <!-- 标题：选定字段的值；▾ 切换记录标题（参照 PixPin_2026-10-18_00-06-14，存视图配置 recordTitleField） -->
        <div class="rd-title">
          <el-popover :hide-after="0" v-if="canSetTitle" v-model:visible="titlePickOpen" trigger="click" placement="bottom-start" :width="440"
                      :show-arrow="false" popper-class="rd-title-pop">
            <template #reference>
              <span class="rd-title-trigger" :class="{ open: titlePickOpen }">
                <span :class="{ 'rd-title-empty': !titleText }">{{ titleText || '未命名记录' }}</span>
                <StIcon name="chevron-down" :size="18" class="rd-title-caret" />
              </span>
            </template>
            <div class="rd-tp-head">切换记录标题</div>
            <div class="rd-tp-list">
              <div v-for="f in titleCandidates" :key="f.field_name" class="rd-tp-item" @click="pickTitle(f)">
                <span class="rd-tp-check"><StIcon v-if="titleField?.field_name === f.field_name" name="check" :size="16" /></span>
                <StIcon :name="fieldIconName(f)" :size="16" class="rd-tp-ico" /><span class="rd-tp-name">{{ f.label }}</span>
              </div>
            </div>
          </el-popover>
          <span v-else :class="{ 'rd-title-empty': !titleText }">{{ titleText || '未命名记录' }}</span>
        </div>
        <el-dropdown :hide-after="0" v-if="canCreate || canDelete" trigger="click" placement="bottom-end" popper-class="rd-more-pop"
                     @command="(cmd) => $emit('record-action', cmd, record)" @visible-change="(v) => (moreOpen = v)">
          <button class="rd-more st-icon-action" :class="{ open: moreOpen }"><StIcon name="more-h" :size="18" /></button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="canCreate" command="duplicate">生成记录副本</el-dropdown-item>
              <el-dropdown-item v-if="canDelete" command="delete">删除记录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="rd-body">
        <template v-for="row in rows" :key="row.key">
          <div v-if="row.group" class="rd-group" @click="toggle(row.group.id)">
            <StIcon :name="collapsed.has(row.group.id) ? 'chevron-right' : 'chevron-down'" :size="16" class="rd-caret" />
            <span class="rd-gname">{{ row.group.name }}</span>
          </div>
          <template v-if="!row.group || !collapsed.has(row.group.id)">
            <div v-for="f in row.fields" :key="f.field_name" class="rd-row" :class="{ member: !!row.group }">
              <div class="rd-label"><StIcon :name="fieldIconName(f)" :size="16" class="rd-icon" /><span>{{ f.label }}</span></div>
              <div class="rd-value" :class="[`v-${typeOf(f)}`, { editable: canEdit(f), editing: editing === f.field_name, 'keep-pad': !!inlineKind(f) || isEnum(f) }]"
                   :data-field="f.field_name" @click="(e) => onValueClick(f, e)">
                <!-- 文本/数字/日期：面板内联编辑，内边距/字号/行高与展示态一致，边框用内阴影——进出编辑不位移 -->
                <template v-if="editing === f.field_name && inlineKind(f)">
                  <textarea v-if="inlineKind(f) === 'text'" ref="inlineRef" v-model="draft" class="rd-input rd-ta" rows="1"
                            @input="grow" @blur="commitDraft(f)" @keydown.esc.stop.prevent="cancelDraft"
                            @keydown.ctrl.enter.prevent="$event.target.blur()" />
                  <input v-else-if="inlineKind(f) === 'number'" ref="inlineRef" v-model="draft" class="rd-input"
                         @blur="commitDraft(f)" @keydown.enter.prevent="$event.target.blur()" @keydown.esc.stop.prevent="cancelDraft" />
                  <el-date-picker v-else ref="inlineRef" v-model="draft" class="rd-date" popper-class="rd-date-pop"
                                  :type="f.options?.includeTime ? 'datetime' : 'date'" value-format="YYYY-MM-DD HH:mm:ss"
                                  :format="dayjsDateFormat(f.options || {})"
                                  :placeholder="dayjsDateFormat(f.options || {})" :prefix-icon="NoIcon"
                                  @change="(v) => commit(f, v || null, true)" @visible-change="(v) => !v && (editing = null)" />
                </template>
                <SmartCellEditor v-else-if="editing === f.field_name" :key="`${record.id}:${f.field_name}`"
                                 :field="effOf(f)" :record="record"
                                 @commit="(v) => commit(f, v, true)" @commit-soft="(v) => commit(f, v, false)"
                                 @cancel="editing = null" @collapse="editing = null"
                                 @add-option="(label) => { editing = null; $emit('add-option', { row: record, field: f, label }) }"
                                 @open-config="(x) => $emit('open-config', x)" />
                <!-- 复选框：展示即操作（单击切换） -->
                <SmartCell v-else-if="typeOf(f) === 'checkbox'" :field="f" :record="record" />
                <template v-else-if="isEmpty(f)">
                  <span v-if="typeOf(f) === 'progress'" class="rd-ph-bar" />
                  <span v-else-if="typeOf(f) === 'image'" class="rd-ph-box">{{ placeholderOf(f) }}</span>
                  <span v-else class="rd-ph">{{ placeholderOf(f) }}</span>
                </template>
                <!-- 单选/多选：彩色标签 + ✕（可编辑时 ✕ 直接移除） -->
                <span v-else-if="isEnum(f)" class="rd-tags">
                  <span v-for="o in enumTags(f)" :key="o.id" class="rd-tag"
                        :style="o.raw ? {} : { background: optionColor(o.color).value, color: optionColor(o.color).text }">
                    {{ o.label }}<span v-if="canEdit(f)" class="rd-tag-x" @click.stop="removeTag(f, o.id)">✕</span>
                  </span>
                </span>
                <!-- 日期类：按字段日期格式显示（与表格单元格 formatDate 一致），编辑框同格式，进出编辑文字不变 -->
                <span v-else-if="isDateType(f)">{{ fmtDate(record[f.field_name], f) }}</span>
                <SmartCell v-else :field="f" :record="record" />
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>
    <!-- 不可编辑提示（同表格单元格：「X不可直接编辑 · 修改设置」/ 无权限提示），值区下方弹出 -->
    <teleport to="body">
      <div v-if="blockedHint" class="st-blocked-hint rd-blocked-hint" :style="{ left: `${blockedHint.x}px`, top: `${blockedHint.y}px` }" @mousedown.stop>
        <span>{{ blockedHint.text }}</span>
        <span v-if="blockedHint.field" class="st-blocked-link" @click="openBlockedConfig">修改设置</span>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, h, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import SmartCell from '../grid/SmartCell.vue'
import SmartCellEditor from '../grid/SmartCellEditor.vue'
import StIcon from '../icons/StIcon.vue'
import { dayjsDateFormat, formatCurrency, formatDate, formatNumber } from '../../../smart/utils/format.js'
import { BLOCKED_CONFIGURABLE, BLOCKED_EDIT_TEXT, optionColor, regOf } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  record: Object,
  fields: { type: Array, default: () => [] },
  view: { type: Object, default: () => ({ config: {} }) },
  columnGroups: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  canEditCell: { type: Function, default: null },
  canCreate: { type: Boolean, default: true },
  canDelete: { type: Boolean, default: true },
  titleField: { type: String, default: null },     // 视图配置 recordTitleField
  canSetTitle: { type: Boolean, default: false },  // 有视图管理权限才能切换记录标题
})
const emit = defineEmits(['cell-commit', 'record-action', 'add-option', 'open-config', 'set-title-field'])

const moreOpen = ref(false)

// 两种容器共用编辑状态；切换记录时退出当前字段编辑。
const editing = ref(null)   // 正在编辑的 field_name
watch(() => props.record?.id, () => { editing.value = null })

// 字段顺序 = 视图 fieldOrder（与表格设置同源；隐藏字段在详情里照常展示）
const orderedFields = computed(() => {
  const order = props.view?.config?.fieldOrder
  const fs = [...props.fields]
  if (order?.length) {
    const idx = new Map(order.map((n, i) => [n, i]))
    fs.sort((a, b) => (idx.get(a.field_name) ?? 999) - (idx.get(b.field_name) ?? 999))
  }
  return fs
})

// ---------- 记录标题：可作标题的字段（能以一行文字表达的类型；选项/人员/附件/关联等不列） ----------
const TITLE_TYPES = ['text', 'url', 'number', 'currency', 'percent', 'progress', 'date',
                     'createdTime', 'lastModifiedTime', 'autoNumber', 'formula', 'lookup', 'ai']
const titleCandidates = computed(() => orderedFields.value.filter(f => TITLE_TYPES.includes(f.field_type)
  && !(f.field_type === 'ai' && ['singleSelect', 'multiSelect'].includes(f.options?.outputType))))
// 视图指定的标题字段；未指定（或已失效）时取第一个候选字段
const titleField = computed(() => titleCandidates.value.find(f => f.field_name === props.titleField) || titleCandidates.value[0] || null)
const titleText = computed(() => {
  const r = props.record
  const f = titleField.value
  return r && f ? titleValueText(f, r[f.field_name]) : ''
})
function titleValueText(f, v) {
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return ''
  const t = typeOf(f)
  if (isDateType(f)) return fmtDate(v, f)
  if (t === 'currency') return formatCurrency(v, f.options || {})
  if (t === 'number') return formatNumber(v, f.options || {})
  if (t === 'percent') return `${v}%`
  if (t === 'url') return v.text || v.url || ''
  if (Array.isArray(v)) return v.join('、')
  return String(v)
}
const titlePickOpen = ref(false)
function pickTitle(f) {
  titlePickOpen.value = false
  if (f.field_name !== titleField.value?.field_name) emit('set-title-field', f.field_name)
}

// 行序列：散列字段 + 编组节（编组内字段聚合到组下）
const rows = computed(() => {
  const gs = props.columnGroups.filter(g => (g.field_names || []).length)
  const emitted = new Set()
  const out = []
  for (const f of orderedFields.value) {
    const g = gs.find(x => x.field_names.includes(f.field_name))
    if (!g) out.push({ key: f.field_name, fields: [f] })
    else if (!emitted.has(g.id)) {
      emitted.add(g.id)
      out.push({ key: `g_${g.id}`, group: g, fields: orderedFields.value.filter(x => g.field_names.includes(x.field_name)) })
    }
  }
  return out
})
const collapsed = ref(new Set())
function toggle(id) {
  const s = new Set(collapsed.value)
  s.has(id) ? s.delete(id) : s.add(id)
  collapsed.value = s
}

// AI 字段按输出类型编辑/展示（同 SmartGrid.effOf）
const effCache = new WeakMap()
function effOf(field) {
  if (field?.field_type !== 'ai') return field
  let e = effCache.get(field)
  if (!e) { e = { ...field, field_type: field.options?.outputType || 'text', __aiField: true }; effCache.set(field, e) }
  return e
}
const typeOf = (f) => effOf(f)?.field_type
const isEnum = (f) => ['singleSelect', 'multiSelect'].includes(typeOf(f))

function canEdit(f) {
  if (props.readonly || regOf(f).readonly) return false
  return props.canEditCell ? props.canEditCell(props.record, f) : true
}

function isEmpty(f) {
  const v = props.record?.[f.field_name]
  return v == null || v === '' || (Array.isArray(v) && !v.length)
}

// 空值占位提示（参照稿：文本「请输入」、数字「请输入数字」、日期「YYYY年M月D日」…）
const PLACEHOLDERS = {
  text: '请输入', url: '请输入链接',
  number: '请输入数字', percent: '请输入数字', currency: '请输入数字',
  singleSelect: '请选择', multiSelect: '请选择',
  member: '请添加人员', group: '请添加群聊', chat: '请添加群聊',
  image: '添加图片', file: '添加文件', relation: '请选择记录',
}
function placeholderOf(f) {
  if (!canEdit(f)) return ''
  if (typeOf(f) === 'date') return dayjsDateFormat(f.options || {})   // 日期：按字段格式提示，如 YYYY-MM-DD
  return PLACEHOLDERS[typeOf(f)] ?? '请输入'
}

function enumTags(f) {
  const v = props.record[f.field_name]
  const ids = Array.isArray(v) ? v : [v]
  const opts = effOf(f).options?.options || []
  return ids.filter(id => id != null && id !== '').map(id => {
    const o = opts.find(x => x.id === id)
    return o ? { id, label: o.label, color: o.color } : { id, label: String(id), raw: true }
  })
}
function removeTag(f, id) {
  const v = props.record[f.field_name]
  if (typeOf(f) === 'multiSelect') {
    const rest = (Array.isArray(v) ? v : [v]).filter(x => x !== id)
    commit(f, rest.length ? rest : null, true)
  } else commit(f, null, true)
}

// 面板内联编辑的类型（其余走单元格编辑器 SmartCellEditor）
const INLINE_KINDS = { text: 'text', number: 'number', percent: 'number', currency: 'number', date: 'date' }
const inlineKind = (f) => INLINE_KINDS[typeOf(f)] || null
const NoIcon = { render: () => h('span') }   // 日期框去掉前置日历图标，文字与展示态同一起点
const draft = ref('')
const inlineRef = ref(null)
let draftCancelled = false

// 日期展示：与表格单元格同一个 formatDate（按字段日期格式），日期编辑框 format 同源（dayjsDateFormat）
const isDateType = (f) => ['date', 'createdTime', 'lastModifiedTime'].includes(typeOf(f))
const fmtDate = (v, f) => formatDate(v, f.options || {})

// ---------- 不可编辑提示（文案与表格单元格共用 BLOCKED_EDIT_TEXT） ----------
const blockedHint = ref(null)   // {x, y, text, field}
function showBlockedHint(f, el) {
  const ft = f.field_type   // AI 字段按原类型判定（只读）
  const typeText = BLOCKED_EDIT_TEXT[ft] || (ft === 'ai' ? 'AI 字段内容由 AI 生成，不可直接编辑' : null)
  const text = typeText || (props.readonly ? '你没有编辑该表格的权限' : '你没有编辑该单元格的权限')
  const r = el.getBoundingClientRect()
  const x = Math.max(8, Math.min(r.left, window.innerWidth - 300))
  const y = r.bottom + 60 > window.innerHeight ? r.top - 46 : r.bottom + 6   // 下方放不下就放上方
  blockedHint.value = { x, y, text, field: typeText && BLOCKED_CONFIGURABLE.includes(ft) && !props.readonly ? f : null }
}
function hideBlockedHint() { blockedHint.value = null }
function openBlockedConfig() {
  const f = blockedHint.value?.field
  hideBlockedHint()
  if (f) emit('open-config', f)
}
watch(() => props.record?.id, hideBlockedHint)

function onValueClick(f, e) {
  if (editing.value === f.field_name) return
  if (!canEdit(f)) { showBlockedHint(f, e.currentTarget); return }
  if (typeOf(f) === 'checkbox') { commit(f, !props.record[f.field_name], true); return }
  const kind = inlineKind(f)
  if (kind) {
    const v = props.record[f.field_name]
    draft.value = v ?? ''
    draftCancelled = false
  }
  editing.value = f.field_name
  if (!kind) return
  nextTick(() => {
    const el = [].concat(inlineRef.value)[0]
    if (!el) return
    if (kind === 'date') { el.handleOpen?.() || el.focus?.(); return }
    grow({ target: el })
    el.focus({ preventScroll: true })
    const end = String(draft.value).length
    el.setSelectionRange?.(end, end)
  })
}
// textarea 按内容增高（单行时与展示态同为 22px 一行）
function grow(e) {
  const ta = e.target
  if (ta?.tagName !== 'TEXTAREA') return
  ta.style.height = 'auto'
  ta.style.height = `${ta.scrollHeight}px`
}
function commitDraft(f) {
  if (draftCancelled || editing.value !== f.field_name) return
  let v = draft.value
  if (inlineKind(f) === 'number') {
    if (v === '' || v == null) v = null
    else if (Number.isNaN(Number(v))) { ElMessage.warning('请输入数字'); editing.value = null; return }
    else v = Number(v)
  }
  commit(f, v === '' ? null : v, true)
}
function cancelDraft() {
  draftCancelled = true
  editing.value = null
}
function commit(f, value, close) {
  if (close) editing.value = null
  emit('cell-commit', { row: props.record, field: f, value })
}

// 上传/链接/进度编辑器没有自己的失焦提交：点到值区与浮层之外即退出编辑。
// 其余编辑器（文本/选项/日期/人员/关联）自己在失焦或面板关闭时提交，不能抢先卸载
const SELF_CLOSING = ['inline', 'select', 'date', 'member', 'relation']
function onDocMousedown(e) {
  if (blockedHint.value && !e.target.closest?.('.rd-blocked-hint')) hideBlockedHint()
  if (!editing.value) return
  const f = props.fields.find(x => x.field_name === editing.value)
  if (!f || SELF_CLOSING.includes(regOf(effOf(f)).editor)) return
  if (e.target.closest?.(`.rd-value[data-field="${editing.value}"], .el-popper, .el-upload`)) return
  editing.value = null
}
document.addEventListener('mousedown', onDocMousedown, true)
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocMousedown, true))
</script>

<style scoped>
.rd-content { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; overflow: hidden; }
/* 统一外框内的内容区，独立滚动 */
.rd-card { display: flex; flex-direction: column; flex: 1; min-height: 0;  }
.rd-head { display: flex; align-items: flex-start; gap: 12px; padding: 20px 16px 8px 24px; flex: none; }
.rd-title { flex: 1; min-width: 0; font-size: 22px; line-height: 30px; font-weight: 500; color: var(--st-text-1); word-break: break-all; }
.rd-title-empty { color: var(--st-text-4); }
/* 标题 ▾：整块可点，hover 浅灰底 */
.rd-title-trigger { display: inline-flex; align-items: center; gap: 4px; max-width: 100%; margin-left: -6px; padding: 0 6px;
  border-radius: 6px; cursor: pointer; }
.rd-title-trigger:hover, .rd-title-trigger.open { background: var(--st-bg-hover); }
.rd-title-caret { flex: none; color: var(--st-text-1); }
.rd-more { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0;
           border: none; border-radius: 6px; background: transparent; color: var(--st-text-1); cursor: pointer; }
.rd-more:hover, .rd-more.open { background: var(--st-bg-active); }
.rd-body { flex: 1; min-height: 0; overflow: auto; padding: 4px 16px 16px 16px; }
/* 字段行：左列图标 + 字段名（可换行），右列值 */
.rd-row { display: flex; align-items: flex-start; gap: 12px; min-height: 44px; padding: 4px 0; box-sizing: border-box; }
.rd-row.member { margin-left: 8px; padding-left: 14px; border-left: 1px solid #DCDEE0; }
.rd-label { display: flex; align-items: flex-start; gap: 8px; width: 190px; flex: none; padding-top: 7px;
            font-size: 15px; line-height: 22px; color: var(--st-text-1); word-break: break-all; }
.rd-row.member .rd-label { width: 168px; }
/* 图标/名称样式与表格设置面板一致（图标 16px 灰、名称 15px 深色、间距 8px） */
.rd-icon { color: var(--st-text-2); flex: none; margin-top: 3px; }
.rd-value { position: relative; flex: 1; min-width: 0; min-height: 36px; padding: 7px 8px; margin-left: -8px; box-sizing: border-box;
            border-radius: 6px; font-size: 15px; line-height: 22px; color: var(--st-text-1); word-break: break-all; }
.rd-value.editable { cursor: pointer; }
.rd-value.editable:not(.editing):hover { background: var(--st-bg-hover); }
/* 编辑态：内边距不变（与展示态同高），蓝色边框用内阴影画、不占布局 */
.rd-value.editing { background: #fff; box-shadow: inset 0 0 0 2px var(--st-primary); }
/* 其余编辑器（人员/关联/上传…）自带边框，值区让出内边距 */
.rd-value.editing:not(.keep-pad) { padding: 0; box-shadow: none; }
.rd-input { display: block; width: 100%; margin: 0; padding: 0; border: none; outline: none; background: transparent;
            font: inherit; font-size: 15px; line-height: 22px; height: 22px; color: var(--st-text-1); }
.rd-ta { resize: none; overflow: hidden; word-break: break-all; }
/* 日期：输入框去边框/内边距，文字与展示态同位置 */
/* 块级 flex：EP 默认 inline-flex + vertical-align:middle 会在行框里下沉 1px */
.rd-date.el-date-editor, .rd-value :deep(.rd-date.el-date-editor) { display: flex; width: 100%; height: 22px; }
.rd-value :deep(.rd-date .el-input__wrapper) { padding: 0; box-shadow: none !important; background: transparent; height: 22px; }
.rd-value :deep(.rd-date .el-input__prefix) { display: none; }
.rd-value :deep(.rd-date .el-input__inner) { height: 22px; line-height: 22px; font-size: 15px; font-family: inherit; color: var(--st-text-1); }
/* 展示态：去掉单元格排版（13px / flex / 单行），与编辑框同为 15px·22px 块级——进出编辑文字不动 */
.rd-value :deep(.smart-cell) { display: block; font-size: 15px; line-height: 22px; min-height: 22px; width: auto;
  white-space: normal; overflow: visible; }
.rd-value :deep(.smart-cell .txt) { white-space: pre-wrap; overflow: visible; text-overflow: clip; }
.rd-ph { color: var(--st-text-4); }
.rd-ph-bar { display: block; width: 60%; height: 22px; border-radius: 4px; background: var(--st-bg-hover); }
.rd-ph-box { display: block; margin: -7px -8px; padding: 7px 8px; border-radius: 6px; background: var(--st-bg-hover); color: var(--st-text-4); }
/* 单选/多选标签：22px 高，单行时值区与其它字段同为 36px */
.rd-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.rd-tag { display: inline-flex; align-items: center; gap: 4px; padding: 0 8px; border-radius: 4px; font-size: 14px; line-height: 22px; }
.rd-value.editable .rd-tags { padding-right: 22px; }   /* 与编辑态 ▼ 让位一致，换行位置不变 */
.rd-tag-x { opacity: .6; cursor: pointer; font-size: 12px; }
.rd-tag-x:hover { opacity: 1; }
/* 编组节：∨ 组名 */
.rd-group { display: flex; align-items: center; gap: 6px; height: 44px; cursor: pointer; user-select: none; font-size: 15px; color: var(--st-text-1); }
.rd-caret { color: var(--st-text-2); }
/* 编辑态：编辑器撑满值区 */
.rd-value.editing :deep(.cell-editor) { width: 100%; }
/* 单选/多选编辑态：去掉单元格锚点自带的边框/内边距/阴影，标签排版与展示态一致（边框由值区内阴影画）；
   ▼ 相对值区定位，不占文字流——进出编辑标签不动 */
.rd-value.editing :deep(.sel-anchor) { position: static; min-height: 22px; padding: 0 22px 0 0; gap: 6px; border: none;
  border-radius: 0; background: transparent; box-shadow: none; align-content: flex-start; }
.rd-value.editing :deep(.sel-anchor .opt-tag) { gap: 0; padding: 0 8px; font-size: 14px; line-height: 22px; }
.rd-value.editing :deep(.sel-anchor .tag-x) { margin-left: 4px; font-size: 12px; }
.rd-value.editing :deep(.sel-anchor .chev) { top: 6px; right: 6px; }
</style>

<style>
.rd-more-pop .el-dropdown-menu__item { font-size: 15px; padding: 8px 28px; }
/* 切换记录标题下拉：灰色小标题 + 字段列表（✓ + 类型图标 + 名称），超高滚动 */
.rd-title-pop.el-popover.el-popper { padding: 8px 6px; border-radius: 10px; }
.rd-title-pop .rd-tp-head { padding: 6px 12px 8px; font-size: 14px; color: var(--st-text-3); }
.rd-title-pop .rd-tp-list { max-height: 520px; overflow-y: auto; }
.rd-title-pop .rd-tp-item { display: flex; align-items: center; gap: 10px; height: 40px; padding: 0 12px; border-radius: 6px;
  cursor: pointer; font-size: 15px; color: var(--st-text-1); }
.rd-title-pop .rd-tp-item:hover { background: var(--st-bg-hover); }
.rd-title-pop .rd-tp-check { display: inline-flex; width: 18px; flex: none; color: var(--st-primary); }
.rd-title-pop .rd-tp-ico { flex: none; color: var(--st-text-2); }
.rd-title-pop .rd-tp-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
