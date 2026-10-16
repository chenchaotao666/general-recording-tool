<template>
  <!-- 筛选面板（设计文档 §5.1）：条件卡片列表 + 组合方式（全部/任一）+ 作用域切换（仅你可见/对所有人）+ pin 图钉。
       草稿模式：面板内自由编辑，点「确定」才落库——避免防抖保存剔除不完整行导致"刚添加就消失" -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="420" popper-class="filter-popover">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head">
        <b>筛选</b>
        <el-radio-group :model-value="scope" size="small" @change="$emit('scope-change', $event)">
          <el-radio-button value="personal">调整仅你可见</el-radio-button>
          <el-radio-button value="shared">对所有人生效</el-radio-button>
        </el-radio-group>
      </div>

      <div v-if="draft.length" class="conj-row">
        满足以下
        <el-select :teleported="false" v-model="draftConj" size="small" class="conj-sel">
          <el-option value="and" label="全部条件" />
          <el-option value="or" label="任一条件" />
        </el-select>
      </div>

      <div v-for="(c, i) in draft" :key="c.id || i" class="cond-card">
        <!-- 展开态：字段选择 + 操作图标（删除/固定/收起） -->
        <template v-if="isOpen(c)">
          <div class="cond-head">
            <StIcon :name="fieldOf(c)?.field_type || 'text'" :size="15" class="f-icon" />
            <el-select :teleported="false" :model-value="c.fieldId" size="small" class="c-field" placeholder="选择字段"
                       @change="(v) => update(i, { fieldId: v, operator: defaultOp(v), value: undefined })">
              <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
            </el-select>
            <span class="h-act" title="删除条件" @click="remove(i)"><StIcon name="minus-circle" :size="15" /></span>
            <span class="h-act pin" :class="{ on: c.pinned }" title="固定到工具栏" @click="update(i, { pinned: !c.pinned })"><StIcon name="pin" :size="15" /></span>
            <span class="h-act" title="收起" @click="toggleOpen(c)"><StIcon name="chevron-up" :size="15" /></span>
          </div>
          <el-select :teleported="false" :model-value="opsOf(c).includes(c.operator) ? c.operator : null"
                     size="small" class="c-op" placeholder="条件"
                     @change="(v) => update(i, { operator: v })">
            <el-option v-for="op in opsOf(c)" :key="op" :value="op" :label="OP_LABELS[op]" />
          </el-select>
          <ConditionValue v-if="!NO_VALUE_OPS.includes(c.operator)" :field="fieldOf(c)"
                          :operator="c.operator" :value="c.value"
                          @update="(v) => update(i, { value: v })" />
        </template>
        <!-- 收起态：单行摘要（图标 + 字段名 + 条件与取值）；hover 显示删除/固定 -->
        <div v-else class="cond-summary" @click="toggleOpen(c)">
          <StIcon :name="fieldOf(c)?.field_type || 'text'" :size="15" class="f-icon" />
          <span class="s-field">{{ fieldOf(c)?.label || '选择字段' }}</span>
          <span class="s-text">{{ summaryOf(c) }}</span>
          <span class="h-act hover-only" title="删除条件" @click.stop="remove(i)"><StIcon name="minus-circle" :size="15" /></span>
          <span class="h-act pin hover-only" :class="{ on: c.pinned }" title="固定到工具栏"
                @click.stop="update(i, { pinned: !c.pinned })"><StIcon name="pin" :size="15" /></span>
          <span class="h-act" title="展开"><StIcon name="chevron-down" :size="15" /></span>
        </div>
      </div>

      <el-button link type="primary" size="small" class="add-btn" @click="add">＋ 添加筛选条件</el-button>
      <div class="panel-foot">
        <el-button size="small" @click="cancel">取消</el-button>
        <el-button size="small" type="primary" @click="confirm">确定</el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import ConditionValue from './ConditionValue.vue'
import StIcon from '../icons/StIcon.vue'
import { filterOpsOf, OP_LABELS, NO_VALUE_OPS } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  conditions: { type: Array, default: () => [] },
  conjunction: { type: String, default: 'and' },
  scope: { type: String, default: 'personal' },
})
const emit = defineEmits(['update:visible', 'change', 'scope-change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })
const members = inject('smartMembers', { value: [] })

// 草稿：打开时从 props 复制，编辑只动草稿；确定才 emit 给父级（一次落库）
const draft = ref([])
const draftConj = ref('and')
// 卡片展开集合：打开面板时完整条件默认收起（只显摘要），不完整条件保持展开
const openIds = ref(new Set())
watch(() => props.visible, (v) => {
  if (!v) return
  draft.value = props.conditions.map((c) => ({ ...c }))
  draftConj.value = props.conjunction || 'and'
  openIds.value = new Set(draft.value.filter((c) => !isComplete(c)).map((c) => c.id))
})

function fieldOf(c) { return props.fields.find(f => f.field_name === c.fieldId) }
function opsOf(c) { return fieldOf(c) ? filterOpsOf(fieldOf(c)) : [] }
function defaultOp(fieldName) {
  const f = props.fields.find(x => x.field_name === fieldName)
  return f ? filterOpsOf(f)[0] : null
}
function isComplete(c) {
  if (!c.fieldId) return false
  if (NO_VALUE_OPS.includes(c.operator)) return true
  const v = c.value
  return v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length)
}
function isOpen(c) { return openIds.value.has(c.id) }
function toggleOpen(c) {
  const s = new Set(openIds.value)
  s.has(c.id) ? s.delete(c.id) : s.add(c.id)
  openIds.value = s
}

// 收起摘要：运算符 + 取值（枚举/人员 id → 标签）
function summaryOf(c) {
  const f = fieldOf(c)
  if (!f) return ''
  let vs = ''
  if (!NO_VALUE_OPS.includes(c.operator)) {
    const v = Array.isArray(c.value) ? c.value : [c.value]
    if (['singleSelect', 'multiSelect'].includes(f.field_type)) {
      const opts = f.options?.options || []
      vs = v.map(id => opts.find(o => o.id === id)?.label ?? id).join('、')
    } else if (['member', 'createdBy', 'lastModifiedBy'].includes(f.field_type)) {
      const ms = members.value || []
      vs = v.map(id => ms.find(m => m.id === id)?.name ?? id).join('、')
    } else {
      vs = v.filter(x => x !== undefined && x !== null).join('、')
    }
  }
  return `${OP_LABELS[c.operator] || ''}${vs ? ` ${vs}` : ''}`
}

function update(i, patch) {
  draft.value = draft.value.map((c, j) => (j === i ? { ...c, ...patch } : c))
}
function add() {
  const id = `c_${Date.now()}`
  draft.value = [...draft.value, { id, fieldId: null, operator: null, value: undefined, pinned: false }]
  openIds.value = new Set(openIds.value).add(id)
}
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i) }

function cancel() { emit('update:visible', false) }
function confirm() {
  // 只提交完整条件（选了字段的）；空行视为用户放弃
  emit('change', draft.value.filter((c) => c.fieldId), draftConj.value)
  emit('update:visible', false)
}
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-foot { display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid #ebeef5; padding-top: 8px; }

/* 组合方式行：下拉做成无边框的文字链形态（贴近参照图） */
.conj-row { display: flex; align-items: center; gap: 6px; color: var(--el-text-color-regular); font-size: 13px; }
.conj-sel { width: 96px; }
.conj-sel :deep(.el-select__wrapper) { box-shadow: none; background: transparent; }
.conj-sel :deep(.el-select__selected-item) { color: var(--el-color-primary); }

/* 条件卡片 */
.cond-card { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 8px 10px;
             display: flex; flex-direction: column; gap: 8px; background: var(--el-fill-color-blank); }
.cond-head { display: flex; align-items: center; gap: 6px; }
.f-icon { flex: none; color: var(--st-text-2); }
.c-field { flex: 1; min-width: 0; }
.c-field :deep(.el-select__wrapper) { box-shadow: none; background: transparent; font-weight: 600; }
.c-op { width: 100%; }
.h-act { flex: none; cursor: pointer; color: var(--st-text-3); padding: 0 2px; display: inline-flex; }
.h-act:hover { color: var(--st-primary); }
/* 收起态的删除/固定：仅卡片 hover 时显示（已固定的图钉常显，作为状态标识） */
.hover-only { visibility: hidden; }
.cond-card:hover .hover-only { visibility: visible; }
.cond-card .pin.on { visibility: visible; }
.pin { opacity: 0.35; }
.pin.on { opacity: 1; }

/* 收起摘要行 */
.cond-summary { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.s-field { flex: none; font-weight: 600; }
.s-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
          color: var(--el-text-color-secondary); font-size: 13px; }
.add-btn { align-self: flex-start; }
</style>
