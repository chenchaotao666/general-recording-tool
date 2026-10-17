<template>
  <!-- 权限配置（单个条目）：等级下拉 + 视图管理开关 + 记录权限(行) + 字段权限(列)
       对齐参照 内容权限-仅浏览.png（实为可编辑等级）/ 内容权限-可编辑.png（实为仅浏览）/ 内部权限-全部权限.png -->
  <div class="pe">
    <div class="pe-card pe-head">
      <div class="pe-title"><StIcon name="table-solid" :size="16" />{{ entryName }} 的权限</div>
      <el-select :model-value="p.level" class="pe-level" :teleported="false" @update:model-value="setLevel">
        <el-option v-for="o in levelOptions" :key="o.value" :value="o.value" :label="o.label" />
      </el-select>
      <template v-if="!isDashboard && (p.level === 'EDIT' || (p.level === 'FULL' && expanded))">
        <div class="pe-sep" />
        <div class="pe-row"><span class="pe-indent">可以新建、删除、修改视图</span>
          <el-switch :model-value="p.viewManage" @update:model-value="(v) => patch({ viewManage: v })" />
        </div>
      </template>
    </div>

    <template v-if="!isDashboard && p.level !== 'NONE'">
      <!-- ---------- 记录权限（行） ---------- -->
      <div class="pe-sec">记录权限(行)
        <el-tooltip content="控制成员可以查看、编辑哪些记录" placement="top"><StIcon name="info" :size="15" class="pe-i" /></el-tooltip>
      </div>
      <div v-if="warnText" class="pe-warn-inline">{{ warnText }}</div>

      <div v-if="p.level === 'FULL' && !expanded" class="pe-card pe-summary">
        <StIcon name="table-solid" :size="15" />可以编辑、新增、删除所有记录。<a class="pe-link" @click="expanded = true">更改</a>
      </div>
      <div v-else class="pe-card">
        <!-- 仅浏览：查看范围 -->
        <template v-if="p.level === 'VIEW'">
          <div class="pe-row">
            <span>可以查看的记录范围</span>
            <el-radio-group :model-value="p.record.viewScope" @update:model-value="(v) => patchRec({ viewScope: v })">
              <el-radio value="ALL">全部 {{ recordTotal }} 条记录</el-radio>
              <el-radio value="PARTIAL">仅部分记录</el-radio>
            </el-radio-group>
          </div>
          <div v-if="p.record.viewScope === 'PARTIAL'" class="pe-cond-box">
            <div class="pe-cond-title">满足此条件时才可查看</div>
            <PermCondRow v-for="(c, i) in p.record.viewConditions" :key="i" :cond="c" :fields="condFields" allow-viewer
                         @update="(nc) => setCond('viewConditions', i, nc)" @remove="removeCond('viewConditions', i)" />
            <button class="pe-add-cond" @click="addCond('viewConditions')"><StIcon name="plus" :size="13" />添加条件</button>
          </div>
        </template>
        <!-- 可编辑 / 全部权限：编辑范围 + fallback + 增删开关 -->
        <template v-else>
          <div class="pe-row">
            <span>可以编辑的记录范围</span>
            <el-radio-group :model-value="p.record.editScope" @update:model-value="(v) => patchRec({ editScope: v })">
              <el-radio value="ALL">全部 {{ recordTotal }} 条记录</el-radio>
              <el-radio value="PARTIAL">仅部分记录</el-radio>
            </el-radio-group>
          </div>
          <div v-if="p.record.editScope === 'PARTIAL'" class="pe-cond-box">
            <div class="pe-cond-title">满足此条件时可编辑，否则
              <el-dropdown trigger="click" @command="(v) => patchRec({ editFallback: v })">
                <a class="pe-link">{{ p.record.editFallback === 'NO_ACCESS' ? '不可查看' : '只可查看' }}<StIcon name="chevron-down" :size="12" /></a>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="VIEW_ONLY">只可查看</el-dropdown-item>
                    <el-dropdown-item command="NO_ACCESS">不可查看</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <PermCondRow v-for="(c, i) in p.record.editConditions" :key="i" :cond="c" :fields="condFields" allow-viewer
                         @update="(nc) => setCond('editConditions', i, nc)" @remove="removeCond('editConditions', i)" />
            <button class="pe-add-cond" @click="addCond('editConditions')"><StIcon name="plus" :size="13" />添加条件</button>
          </div>
          <div class="pe-sep" />
          <div class="pe-row"><span class="pe-ico-label"><StIcon name="row-add" :size="16" />可以添加记录</span>
            <el-switch :model-value="p.record.add" @update:model-value="(v) => patchRec({ add: v })" />
          </div>
          <div class="pe-sep" />
          <div class="pe-row"><span class="pe-ico-label"><StIcon name="row-del" :size="16" />可以删除记录</span>
            <el-switch :model-value="p.record.delete" @update:model-value="(v) => patchRec({ delete: v })" />
          </div>
        </template>
      </div>

      <!-- ---------- 字段权限（列） ---------- -->
      <div class="pe-sec">字段权限(列)
        <el-tooltip content="控制成员可以查看、首次提交、编辑哪些字段" placement="top"><StIcon name="info" :size="15" class="pe-i" /></el-tooltip>
      </div>
      <div v-if="p.level === 'FULL' && !expanded" class="pe-card pe-summary">
        <StIcon name="colgroup" :size="15" />可以编辑所有字段内容、修改字段设置。<a class="pe-link" @click="expanded = true">更改</a>
      </div>
      <div v-else class="pe-card">
        <div class="pe-row">
          <span class="pe-ico-label"><StIcon name="colgroup" :size="16" />字段中的内容</span>
          <el-radio-group :model-value="p.fields.mode" @update:model-value="setFieldMode">
            <el-radio value="ALL">{{ isView ? '可查看所有内容' : '可编辑所有内容' }}</el-radio>
            <el-radio value="PER_FIELD">按字段设置</el-radio>
          </el-radio-group>
        </div>
        <template v-if="p.fields.mode === 'PER_FIELD'">
          <div class="pe-matrix pe-matrix-new">
            <span class="pm-name">后续新增的字段</span>
            <RightsCells :rights="p.fields.newFieldDefault" :view-only="isView"
                         @change="(r) => patchFields({ newFieldDefault: r })" />
          </div>
          <div class="pe-matrix-box">
            <div class="pe-matrix pe-matrix-master">
              <span class="pm-name">已有字段</span>
              <RightsCells :rights="masterRights" :view-only="isView" :indeterminate="masterMixed"
                           @change="setAllFields" />
            </div>
            <template v-for="blk in fieldBlocks" :key="blk.key">
              <div v-if="blk.group" class="pm-group">{{ blk.group }}</div>
              <div v-for="f in blk.fields" :key="f.field_name" class="pe-matrix">
                <span class="pm-name"><StIcon :name="fieldIconName(f)" :size="15" />{{ f.label }}</span>
                <RightsCells :rights="rightsOf(f)" :view-only="isView" :locked-edit="f.lockedEdit"
                             :forced-view="f.forcedView" @change="(r) => setFieldRights(f, r)" />
              </div>
            </template>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, defineComponent, h, ref, watch } from 'vue'
import { ElCheckbox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import PermCondRow from './PermCondRow.vue'

const props = defineProps({
  modelValue: { type: Object, required: true },     // PermissionProfile
  entryName: { type: String, default: '' },
  entryType: { type: String, default: 'sheet' },
  fields: { type: Array, default: () => [] },       // [{field_name,label,field_type,lockedEdit,forcedView,group}]
  recordTotal: { type: Number, default: 0 },
  levelOptions: { type: Array, required: true },
  warnText: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const p = computed(() => props.modelValue)
const isDashboard = computed(() => props.entryType === 'dashboard')
const isView = computed(() => p.value.level === 'VIEW')
const expanded = ref(false)
watch(() => props.entryName, () => { expanded.value = false })

// 条件可选字段：字段元数据带 field_type，PermCondRow 需要 options（选项）——由父级传入完整字段
const condFields = computed(() => props.fields)

function emitP(next) { emit('update:modelValue', next) }
function patch(obj) { emitP({ ...p.value, ...obj }) }
function patchRec(obj) { emitP({ ...p.value, record: { ...p.value.record, ...obj } }) }
function patchFields(obj) { emitP({ ...p.value, fields: { ...p.value.fields, ...obj } }) }

const DEFAULT_RIGHTS = {
  VIEW: { view: true, firstSubmit: false, edit: false },
  EDIT: { view: true, firstSubmit: true, edit: true },
  FULL: { view: true, firstSubmit: true, edit: true },
  NONE: { view: false, firstSubmit: false, edit: false },
}
function setLevel(level) {
  expanded.value = false
  const base = {
    level, viewManage: level === 'EDIT' || level === 'FULL', schemaEdit: level === 'FULL',
    record: { viewScope: 'ALL', viewConditions: [], editScope: 'ALL', editConditions: [], editFallback: 'VIEW_ONLY',
              add: level !== 'VIEW' && level !== 'NONE', delete: level !== 'VIEW' && level !== 'NONE' },
    fields: { mode: 'ALL', newFieldDefault: { ...DEFAULT_RIGHTS[level] }, items: {} },
  }
  emitP(base)
}

function addCond(key) {
  patchRec({ [key]: [...(p.value.record[key] || []), { fieldId: null, operator: 'eq', value: undefined }] })
}
function setCond(key, i, c) {
  const list = [...(p.value.record[key] || [])]
  list[i] = c
  patchRec({ [key]: list })
}
function removeCond(key, i) {
  patchRec({ [key]: (p.value.record[key] || []).filter((_, j) => j !== i) })
}

// ---------- 字段矩阵 ----------
function normalize(f, r) {
  const out = { ...r }
  if (f?.forcedView) out.view = true
  if (f?.lockedEdit || isView.value) { out.edit = false; out.firstSubmit = false }
  if (!out.view) { out.edit = false; out.firstSubmit = false }
  return out
}
function rightsOf(f) {
  return normalize(f, p.value.fields.items?.[f.field_name] || p.value.fields.newFieldDefault)
}
function setFieldMode(mode) {
  if (mode === 'PER_FIELD') {
    const def = { ...DEFAULT_RIGHTS[p.value.level] }
    const items = {}
    for (const f of props.fields) items[f.field_name] = normalize(f, def)
    patchFields({ mode, newFieldDefault: def, items })
  } else {
    patchFields({ mode })
  }
}
function setFieldRights(f, r) {
  patchFields({ items: { ...(p.value.fields.items || {}), [f.field_name]: normalize(f, r) } })
}
const masterRights = computed(() => {
  const all = props.fields.map(rightsOf)
  const pick = (k) => all.length > 0 && all.filter((r, i) => !(k !== 'view' && props.fields[i].lockedEdit)).every(r => r[k])
  return { view: pick('view'), firstSubmit: pick('firstSubmit'), edit: pick('edit') }
})
const masterMixed = computed(() => {
  const all = props.fields.map(rightsOf)
  const mixed = (k) => all.some(r => r[k]) && !masterRights.value[k]
  return { view: mixed('view'), firstSubmit: mixed('firstSubmit'), edit: mixed('edit') }
})
// 主控复选框：整列批量切换三态
function setAllFields(r) {
  const changedKey = ['edit', 'firstSubmit', 'view'].find(k => r[k] !== masterRights.value[k])
  if (!changedKey) return
  const items = { ...(p.value.fields.items || {}) }
  for (const f of props.fields) {
    const cur = rightsOf(f)
    const next = { ...cur, [changedKey]: r[changedKey] }
    if (changedKey !== 'view' && r[changedKey]) next.view = true
    items[f.field_name] = normalize(f, next)
  }
  patchFields({ items })
}
// 按列编组分组渲染（编组头下挂成员字段）
const fieldBlocks = computed(() => {
  const blocks = []
  for (const f of props.fields) {
    const last = blocks[blocks.length - 1]
    if (last && last.group === (f.group || null)) last.fields.push(f)
    else blocks.push({ key: `${f.group || ''}_${blocks.length}`, group: f.group || null, fields: [f] })
  }
  return blocks
})

// 三态复选框单元：可编辑 / 可首次提交 / 可查看（仅浏览等级只显示「可查看」）
const RightsCells = defineComponent({
  props: { rights: Object, viewOnly: Boolean, lockedEdit: Boolean, forcedView: Boolean, indeterminate: Object },
  emits: ['change'],
  setup(cp, { emit: em }) {
    const cell = (key, label, disabled) => h(ElCheckbox, {
      modelValue: !!cp.rights?.[key], disabled,
      indeterminate: !!cp.indeterminate?.[key],
      'onUpdate:modelValue': (v) => {
        const next = { ...cp.rights, [key]: v }
        if (key === 'view' && !v) { next.edit = false; next.firstSubmit = false }
        if (key !== 'view' && v) next.view = true
        em('change', next)
      },
    }, () => label)
    return () => h('span', { class: 'pm-cells' }, cp.viewOnly
      ? [cell('view', '可查看', cp.forcedView)]
      : [cell('edit', '可编辑', cp.lockedEdit), cell('firstSubmit', '可首次提交', cp.lockedEdit),
         cell('view', '可查看', cp.forcedView)])
  },
})
</script>

<style scoped>
.pe { display: flex; flex-direction: column; gap: 0; }
.pe-card { background: #fff; border-radius: 10px; padding: 14px 20px; margin-bottom: 12px; }
.pe-head { padding: 12px 20px; }
.pe-head > .pe-title { display: inline-flex; }
.pe-title { align-items: center; gap: 10px; font-weight: 600; font-size: 15px; color: var(--st-text-1); }
.pe-head { display: grid; grid-template-columns: 1fr auto; align-items: center; row-gap: 6px; }
.pe-level { width: 220px; }
.pe-sep { grid-column: 1 / -1; height: 1px; background: var(--st-border); margin: 6px 0; }
.pe-head .pe-row { grid-column: 1 / -1; }
.pe-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 40px; font-size: 14px; color: var(--st-text-1); }
.pe-indent { padding-left: 36px; }
.pe-ico-label { display: inline-flex; align-items: center; gap: 10px; }
.pe-ico-label .st-icon { color: var(--st-text-1); }
.pe-sec { display: flex; align-items: center; gap: 4px; font-size: 14px; color: var(--st-text-1); margin: 10px 4px 8px; }
.pe-i { color: var(--st-text-2); cursor: help; }
.pe-warn-inline { font-size: 12px; color: #A86B00; margin: -4px 4px 8px; }
.pe-summary { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--st-text-1); }
.pe-summary .st-icon { color: var(--st-text-1); }
.pe-link { color: var(--st-primary); cursor: pointer; display: inline-flex; align-items: center; gap: 2px; margin-left: 8px; }
.pe-cond-box { background: var(--st-bg-canvas); border-radius: 8px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; margin: 4px 0 6px; }
.pe-cond-title { font-size: 14px; color: var(--st-text-1); display: flex; align-items: center; }
.pe-cond-title .pe-link { margin-left: 0; }
.pe-add-cond { display: flex; align-items: center; justify-content: center; gap: 4px; height: 34px; border: 1px solid var(--st-border); border-radius: 6px; background: #fff; cursor: pointer; font-size: 14px; color: var(--st-text-1); width: calc(100% - 30px); }
.pe-add-cond:hover { background: var(--st-bg-hover); }
.pe-matrix-new { background: var(--st-bg-canvas); border-radius: 8px; padding: 0 16px; margin: 6px 0 10px; min-height: 48px; }
.pe-matrix-box { background: var(--st-bg-canvas); border-radius: 8px; padding: 4px 8px 8px; }
.pe-matrix { display: flex; align-items: center; justify-content: space-between; min-height: 38px; padding: 0 10px; border-radius: 6px; font-size: 14px; }
.pe-matrix:not(.pe-matrix-new):not(.pe-matrix-master):hover { background: var(--st-bg-active); }
.pe-matrix-master { border-bottom: 1px solid var(--st-border); border-radius: 0; margin: 0 2px 6px; min-height: 48px; }
.pm-name { display: inline-flex; align-items: center; gap: 10px; color: var(--st-text-1); }
.pm-name .st-icon { color: var(--st-text-2); }
.pm-group { font-size: 12px; color: var(--st-text-3); padding: 8px 10px 2px; }
:deep(.pm-cells) { display: inline-flex; gap: 18px; }
:deep(.pm-cells .el-checkbox) { margin-right: 0; }
/* 参照稿：选中态只染控件本身，文字保持正文色 */
.pe :deep(.el-radio__input.is-checked + .el-radio__label),
.pe :deep(.el-checkbox__input.is-checked + .el-checkbox__label) { color: var(--st-text-1); }
.pe :deep(.el-checkbox.is-disabled .el-checkbox__label) { color: var(--st-text-4); }
</style>
