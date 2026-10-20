<template>
  <!-- 筛选面板（设计文档 §5.1，对齐参照 docs/智慧表格/表格上方按钮/筛选.png）：
       标题 + 作用域胶囊（调整仅你可见 | 对所有人生效 | ⋯）→「满足以下 全部条件 ▾」→ 条件卡片
       （头：字段 ▾ + ⊖ 📌 ︿；体：运算符 ▾ + 值；人员/选项为内联勾选清单）→「＋ 添加筛选条件」（选择字段下拉）。
       即时生效：本地保留草稿（含未填完的条件），每次变更只把完整条件提交给父级 -->
  <el-popover :hide-after="0" trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="560"
              popper-class="filter-popover st-tbpanel">
    <template #reference><span ref="refEl" class="fp-ref"><slot /></span></template>
    <!-- 高度上限 = 按钮下方可用空间：条件多时中间列表区滚动，标题与「添加筛选条件」常驻可见，不被屏幕底部遮挡 -->
    <div class="fp" :style="{ maxHeight: `${maxH}px` }">
      <div class="fp-head">
        <span class="tbp-title">筛选</span>
        <span class="fp-scope">
          <span class="fp-scope-item" :class="{ on: scope === 'personal' }" @click="$emit('scope-change', 'personal')">调整仅你可见</span>
          <span class="fp-scope-item" :class="{ on: scope === 'shared' }" @click="$emit('scope-change', 'shared')">对所有人生效</span>
          <el-dropdown :hide-after="0" trigger="click" :teleported="false" :popper-options="FIXED_POPPER" @command="onMore">
            <span class="fp-scope-more st-icon-action"><StIcon name="more-h" :size="16" /></span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="clear" :disabled="!draft.length">清空所有条件</el-dropdown-item>
                <el-dropdown-item command="collapse" :disabled="!draft.length">收起所有条件</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </span>
      </div>

      <div v-if="draft.length" class="fp-scroll">
      <div class="fp-conj">满足以下
        <el-dropdown :hide-after="0" trigger="click" :teleported="false" :popper-options="FIXED_POPPER" @command="(v) => { draftConj = v; commit() }">
          <a class="fp-link">{{ draftConj === 'or' ? '任一条件' : '全部条件' }}<StIcon name="chevron-down" :size="12" /></a>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="and">全部条件</el-dropdown-item>
              <el-dropdown-item command="or">任一条件</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div v-for="(c, i) in draft" :key="c.id" class="fp-card">
        <!-- 折叠态只显示字段名，单击整行展开/收起；展开后字段名才变为可切换字段的下拉 -->
        <div class="fp-card-head" @click="toggleOpen(c)">
          <span v-if="!isOpen(c)" class="fp-field static"><StIcon :name="fieldIconName(fieldOf(c))" :size="18" />
            <span class="fp-field-name">{{ fieldOf(c)?.label || '选择字段' }}</span></span>
          <!-- 切换字段：统一「选择字段」面板（编组可折叠，参照 PixPin_2026-10-18_01-05-36） -->
          <el-popover :hide-after="0" v-else :visible="fieldPickId === c.id" @update:visible="(v) => (fieldPickId = v ? c.id : null)" trigger="click"
                      placement="bottom-start" :width="324" :teleported="false" :show-arrow="false"
                      :popper-options="FIXED_POPPER" popper-class="st-tbpanel st-pick-pop">
            <template #reference>
              <span class="fp-field" @click.stop><StIcon :name="fieldIconName(fieldOf(c))" :size="18" />
                {{ fieldOf(c)?.label || '选择字段' }}<StIcon name="chevron-down" :size="13" class="fp-caret" /></span>
            </template>
            <FieldPickList :fields="fields" :column-groups="columnGroups" :selected="c.fieldId"
                           @pick="(f) => { fieldPickId = null; if (f.field_name !== c.fieldId) changeField(i, f.field_name) }" />
          </el-popover>
          <span v-if="!isOpen(c)" class="fp-sum">{{ summaryOf(c) }}</span>
          <span class="fp-acts">
            <el-tooltip :hide-after="0" content="删除条件" placement="top" :show-after="300"><span class="fp-act st-icon-action" @click.stop="remove(i)"><StIcon name="minus-circle" :size="18" /></span></el-tooltip>
            <el-tooltip :hide-after="0" :content="c.pinned ? '取消固定' : '固定到工具栏'" placement="top" :show-after="300">
              <span class="fp-act st-icon-action" :class="{ on: c.pinned }" @click.stop="update(i, { pinned: !c.pinned })"><StIcon name="pin" :size="18" /></span></el-tooltip>
            <span class="fp-vsep" />
            <span class="fp-act st-icon-action" @click.stop="toggleOpen(c)"><StIcon :name="isOpen(c) ? 'chevron-up' : 'chevron-down'" :size="18" /></span>
          </span>
        </div>
        <div v-if="isOpen(c) && fieldOf(c)" class="fp-card-body">
          <!-- 运算符（参照 PixPin_2026-10-18_00-48-13）：当前项 ✓ 在右；展开时触发文字带灰底 -->
          <el-dropdown :hide-after="0" trigger="click" placement="bottom-start" :teleported="false" :popper-options="FIXED_POPPER" popper-class="fp-op-pop"
                       @visible-change="(v) => (opOpenId = v ? c.id : null)" @command="(op) => changeOp(i, op)">
            <a class="fp-op" :class="{ open: opOpenId === c.id }">{{ opLabel(fieldOf(c), c.operator) || '选择条件' }}<StIcon name="chevron-down" :size="14" /></a>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="op in opsOf(c)" :key="op" :command="op">
                  <span class="fp-op-item">{{ opLabel(fieldOf(c), op) }}<StIcon v-if="op === c.operator" name="check" :size="16" class="fp-op-ck" /></span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <template v-if="!NO_VALUE_OPS.includes(c.operator)">
            <!-- 人员 / 选项：内联勾选清单 -->
            <div v-if="isListField(c)" class="fp-list">
              <FilterOptionList :options="listOptions(c)" :selected="c.value || []" :kind="isMemberField(c) ? 'member' : 'enum'"
                                search-mode="toggle" :max-height="240"
                                @toggle="(id) => toggleValue(i, id)" @clear="update(i, { value: [] })" />
            </div>
            <div v-else class="fp-val">
              <ConditionValue :field="fieldOf(c)" :operator="c.operator" :value="c.value" @update="(v) => update(i, { value: v })" />
            </div>
          </template>
        </div>
      </div>
      </div>

      <el-popover :hide-after="0" v-model:visible="picking" trigger="click" placement="bottom-start" :width="324" :teleported="false"
                  popper-class="st-tbpanel st-pick-pop" :show-arrow="false">
        <template #reference><button class="tbp-add"><StIcon name="plus" :size="15" />添加筛选条件</button></template>
        <FieldPickList :fields="fields" :column-groups="columnGroups" @pick="add" />
      </el-popover>
    </div>
  </el-popover>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ConditionValue from './ConditionValue.vue'
import FieldPickList from './FieldPickList.vue'
import FilterOptionList from './FilterOptionList.vue'
import StIcon from '../icons/StIcon.vue'
import { filterOpsOf, NO_VALUE_OPS, opLabel } from '../../../smart/registry/fieldRegistry.js'
import { dateModeLabel, dateModesFor, isCondValueEmpty, isDateModeValue } from '../../../smart/utils/format.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  columnGroups: { type: Array, default: () => [] },
  conditions: { type: Array, default: () => [] },
  conjunction: { type: String, default: 'and' },
  scope: { type: String, default: 'personal' },
})
const emit = defineEmits(['update:visible', 'change', 'scope-change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })
const members = inject('smartMembers', { value: [] })

const MEMBER_TYPES = ['member', 'createdBy', 'lastModifiedBy']
// 面板内的下拉（字段 / 运算符 / 全部条件 / ⋯）一律 :teleported="false" 渲染在面板内部：
// 挂到 body 时点选项会被外层 el-popover 当成"点击外部"直接关掉整个面板（条件设置失败）；
// strategy fixed：不被条件区的滚动容器裁剪
const FIXED_POPPER = { strategy: 'fixed' }
const draft = ref([])
const draftConj = ref('and')
const openIds = ref(new Set())
const picking = ref(false)

// 面板最大高度：按钮底边以下的视口空间 − 弹出间距(12) − 底部留白(16) − 面板上下内边距(42)
const refEl = ref(null)
const maxH = ref(600)
function updateMaxH() {
  const r = refEl.value?.getBoundingClientRect()
  if (!r) return
  maxH.value = Math.max(240, Math.floor(window.innerHeight - r.bottom - 12 - 16 - 42))
}
window.addEventListener('resize', updateMaxH)
onBeforeUnmount(() => window.removeEventListener('resize', updateMaxH))

// 打开时从 props 复制草稿；面板开着期间父级回写不覆盖草稿（保留未填完的条件）
watch(() => props.visible, (v) => {
  if (!v) { picking.value = false; return }
  updateMaxH()
  nextTick(updateMaxH)
  draft.value = props.conditions.map((c) => ({ ...c, id: c.id || `c_${Math.random().toString(36).slice(2, 8)}` }))
  draftConj.value = props.conjunction || 'and'
  openIds.value = new Set()   // 已有条件默认折叠
}, { immediate: true })

const fieldOf = (c) => props.fields.find(f => f.field_name === c.fieldId)
const opsOf = (c) => (fieldOf(c) ? filterOpsOf(fieldOf(c)) : [])
const isMemberField = (c) => MEMBER_TYPES.includes(fieldOf(c)?.field_type)
const isListField = (c) => isMemberField(c) || ['singleSelect', 'multiSelect'].includes(fieldOf(c)?.field_type)
function listOptions(c) {
  const f = fieldOf(c)
  return isMemberField(c)
    ? [{ id: '$viewer', label: '我', viewer: true }, ...(members.value || []).map(m => ({ id: m.id, label: m.name }))]
    : (f?.options?.options || []).map(o => ({ id: o.id, label: o.label, color: o.color }))
}
function isComplete(c) {
  if (!c.fieldId || !c.operator) return false
  if (NO_VALUE_OPS.includes(c.operator)) return true
  return !isCondValueEmpty(c.value)
}
const isOpen = (c) => openIds.value.has(c.id)
function toggleOpen(c) {
  const s = new Set(openIds.value)
  s.has(c.id) ? s.delete(c.id) : s.add(c.id)
  openIds.value = s
}
function summaryOf(c) {
  const f = fieldOf(c)
  if (!f) return ''
  let vs = ''
  if (!NO_VALUE_OPS.includes(c.operator)) {
    const v = Array.isArray(c.value) ? c.value : [c.value]
    if (isDateModeValue(c.value)) vs = dateModeLabel(c.value)   // 日期模式：本周 / 2026-10-01 …
    else if (isListField(c)) {
      const opts = listOptions({ ...c, id: '__sum' })
      vs = v.map(id => opts.find(o => o.id === id)?.label ?? id).join('、')
    } else vs = v.filter(x => x !== undefined && x !== null).join('、')
  }
  return `${opLabel(f, c.operator)}${vs ? ` ${vs}` : ''}`
}

// ---------- 即时生效（防抖提交完整条件） ----------
let timer = null
function commit() {
  clearTimeout(timer)
  timer = setTimeout(() => emit('change', draft.value.filter(isComplete), draftConj.value), 250)
}
function update(i, patch) {
  draft.value = draft.value.map((c, j) => (j === i ? { ...c, ...patch } : c))
  commit()
}
// 切运算符：无值运算符清空取值；日期模式不在新运算符可选范围内（如 等于 本周 → 晚于）也清空，避免保留看不见的条件
const opOpenId = ref(null)
const fieldPickId = ref(null)   // 正在切换字段的条件 id
function changeOp(i, op) {
  const c = draft.value[i]
  let value = NO_VALUE_OPS.includes(op) ? undefined : c.value
  if (isDateModeValue(value) && !dateModesFor(op).some(o => o.value === value.mode)) value = undefined
  update(i, { operator: op, value })
}
function changeField(i, fn) {
  const f = props.fields.find(x => x.field_name === fn)
  update(i, { fieldId: fn, operator: f ? filterOpsOf(f)[0] : null, value: undefined })
}
function toggleValue(i, id) {
  const cur = draft.value[i].value || []
  update(i, { value: cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id] })
}
function add(f) {
  picking.value = false
  const id = `c_${Date.now()}`
  draft.value = [...draft.value, { id, fieldId: f.field_name, operator: filterOpsOf(f)[0], value: undefined, pinned: false }]
  openIds.value = new Set(openIds.value).add(id)
  commit()
}
function remove(i) {
  draft.value = draft.value.filter((_, j) => j !== i)
  commit()
}
function onMore(cmd) {
  if (cmd === 'clear') { draft.value = []; commit() }
  else if (cmd === 'collapse') openIds.value = new Set()
}
</script>

<style>
/* 工具栏面板通用外观（筛选/分组/排序/填色/表格设置/行高）：大圆角 + 柔和阴影 + 粗标题 */
.st-tbpanel.el-popover.el-popper { padding: 22px 24px 20px; border-radius: 12px; border: none; box-shadow: 0 8px 32px rgba(0, 0, 0, .12); }
.st-tbpanel .tbp-title { font-size: 17px; font-weight: 700; color: var(--st-text-1); }
.st-tbpanel .tbp-add { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border: none; border-radius: 6px;
  background: #F2F3F5; color: var(--st-text-1); font-size: 14px; cursor: pointer; align-self: flex-start; }
.st-tbpanel .tbp-add:hover:not(:disabled) { background: #E8E9EB; }
.st-tbpanel .tbp-add:disabled { color: var(--st-text-4); cursor: not-allowed; }
.st-tbpanel .tbp-drag { color: var(--st-text-3); cursor: grab; display: inline-flex; flex: none; }
.st-tbpanel .tbp-del { color: var(--st-text-3); cursor: pointer; display: inline-flex; flex: none; }
.st-tbpanel .tbp-del:hover { color: var(--el-color-danger); }
.st-pick-pop.el-popover.el-popper { padding: 10px 8px; }
/* 运算符下拉：15px 文字、宽行、当前项 ✓ 在右（参照 PixPin_2026-10-18_00-48-13） */
.fp-op-pop.el-dropdown__popper { border-radius: 10px; }
.fp-op-pop .el-dropdown-menu { padding: 6px; border-radius: 10px; }
.fp-op-pop .el-dropdown-menu__item { min-width: 190px; padding: 0 12px; height: 40px; border-radius: 6px; font-size: 15px; color: var(--st-text-1); }
.fp-op-pop .el-dropdown-menu__item:not(.is-disabled):hover { background: var(--st-bg-hover); color: var(--st-text-1); }
.fp-op-pop .fp-op-item { display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 16px; }
.fp-op-pop .fp-op-ck { color: var(--st-primary); }
</style>
<style scoped>
.fp { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.fp-ref { display: inline-flex; }
.fp > :not(.fp-scroll) { flex: none; }   /* 限高时只压缩条件区，标题与「添加筛选条件」保持原高 */
/* 条件区：超出高度上限时独立滚动（右侧留出滚动条位，卡片不贴滚动条） */
.fp-scroll { display: flex; flex-direction: column; gap: 12px; flex: 0 1 auto; min-height: 0; overflow-y: auto;
  margin-right: -10px; padding-right: 10px; }
.fp-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }
.fp-scope { display: inline-flex; align-items: center; background: #E6EEFC; border-radius: 18px; padding: 0 6px 0 4px; height: 34px; }
.fp-scope-item { padding: 0 10px; font-size: 14px; color: var(--st-text-2); cursor: pointer; line-height: 34px; }
.fp-scope-item.on { color: var(--st-primary); }
.fp-scope-more { display: inline-flex; color: var(--st-primary); padding: 4px; cursor: pointer; }
.fp-conj { font-size: 14px; color: var(--st-text-2); display: flex; align-items: center; gap: 4px; }
.fp-link { color: var(--st-primary); cursor: pointer; display: inline-flex; align-items: center; gap: 2px; font-size: 14px; }
/* 条件卡片（参照 PixPin_2026-10-18_00-27-29 取色）：卡片与内框同为 #FAFBFB 底、#EDEFEF 细边，内框四周缩进 6px */
.fp-card { border: 1px solid #EDEFEF; border-radius: 8px; background: #FAFBFB; }
.fp-card-head { display: flex; align-items: center; gap: 8px; padding: 14px 16px 14px 20px; cursor: pointer; }
.fp-field { display: inline-flex; align-items: center; gap: 6px; font-size: 16px; color: var(--st-text-1); cursor: pointer; }
.fp-field.static { flex: none; max-width: 50%; min-width: 0; }
.fp-field-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fp-caret { color: var(--st-text-2); }
.fp-sum { flex: 1; min-width: 0; font-size: 13px; color: var(--st-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fp-acts { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; }
.fp-act { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 4px;
  color: var(--st-text-2); cursor: pointer; }
.fp-act:hover { color: var(--st-text-1); background: #EDEFEF; }
.fp-act.on { color: var(--st-text-1); background: #E2E3E4; }   /* 已固定到工具栏：灰底方块 */
.fp-vsep { width: 1px; height: 14px; background: #DCDEE0; }
.fp-card-body { margin: 0 6px 6px; background: #FAFBFB; border: 1px solid #EDEFEF; border-radius: 8px; padding: 14px 16px 16px;
  display: flex; flex-direction: column; gap: 12px; }
.fp-op { color: #6B6F74; font-size: 15px; cursor: pointer; display: inline-flex; align-items: center; gap: 2px; padding: 2px 4px; border-radius: 4px; }
.fp-op:hover, .fp-op.open { background: #E2E3E4; }
/* 条件值输入：白底 #DADBDD 细边、38px 高、15px 字（参照稿日期框） */
.fp-val :deep(.el-input__wrapper), .fp-val :deep(.el-select__wrapper) {
  background: #fff; box-shadow: 0 0 0 1px #DADBDD inset; min-height: 38px; border-radius: 6px; }
.fp-val :deep(.el-input__wrapper.is-focus), .fp-val :deep(.el-select__wrapper.is-focused) { box-shadow: 0 0 0 1px var(--st-primary) inset; }
.fp-val :deep(.el-input__inner), .fp-val :deep(.el-select__selected-item), .fp-val :deep(.el-select__placeholder) { font-size: 15px; }
.fp-val :deep(.el-select__selected-item:not(.is-transparent)) { color: var(--st-text-1); }
.fp-val :deep(.el-date-editor), .fp-val :deep(.el-input-number) { height: 38px; }
.fp-val :deep(.enum-val) { background: #fff; }
.fp-list { border-top: 1px solid #E8EAEB; padding-top: 12px; display: flex; flex-direction: column; gap: 4px; }
.fp-clear { cursor: pointer; color: var(--st-text-2); }
.fp-clear.dim { color: var(--st-text-4); cursor: default; }
.fp-empty { color: var(--st-text-4); font-size: 13px; padding: 4px 0; }
</style>
