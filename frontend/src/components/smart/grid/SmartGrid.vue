<template>
  <!-- SmartGrid：智能表网格（vxe-table 封装）。
       flatten 行序列：分组标题行 / 数据行（树形缩进）/ 末尾加行。
       视图配置（显隐/列序/列宽/冻结/行高/填色）纯前端应用，数据层不动（设计文档 §1.3 原则 1）。 -->
  <div class="smart-grid" @contextmenu.prevent>
    <vxe-table
      ref="gridRef"
      class="smart-vxe"
      :data="gridRows"
      :height="height"
      border
      :row-config="{ height: rowHeightPx, isHover: true, keyField: '__key' }"
      :column-config="{ resizable: true }"
      :scroll-y="{ enabled: true, gt: 100 }"
      :scroll-x="{ enabled: true, gt: 20 }"
      :show-footer="true"
      :footer-method="footerMethod"
      :row-class-name="rowClass"
      :cell-class-name="cellClass"
      :menu-config="menuConfig"
      @cell-click="onCellClick"
      @cell-dblclick="onCellDblClick"
      @menu-click="onMenuClick"
      @checkbox-all="onCheckAll"
      @checkbox-change="onCheckChange"
    >
      <vxe-column type="checkbox" width="36" fixed="left" />
      <vxe-column width="52" fixed="left" title="#" class-name="col-no">
        <template #default="{ row }">
          <span v-if="row.__rowType === 'group'" class="group-toggle" @click.stop="$emit('toggle-group', row.key)">
            {{ collapsedGroups.has(row.key) ? '▸' : '▾' }}
          </span>
          <span v-else-if="row.__rowType !== 'add'" class="row-no">{{ row.__no }}</span>
        </template>
      </vxe-column>

      <!-- 编组（两级表头）+ 散列字段列 -->
      <template v-for="node in headerTree" :key="node.key">
        <vxe-colgroup v-if="node.isGroup" :title="node.name">
          <vxe-column v-for="f in node.fields" :key="f.field_name" :field="f.field_name"
                      :width="colWidths[f.field_name] || 160"
                      :fixed="isFrozen(f.field_name) ? 'left' : undefined">
            <template #header><FieldHeader :field="f" :view="view" @menu="(e) => $emit('field-menu', f, e)" /></template>
            <template #default="{ row }"><CellSlot :row="row" :field="f" /></template>
          </vxe-column>
        </vxe-colgroup>
        <vxe-column v-else :field="node.field.field_name" :width="colWidths[node.field.field_name] || 160"
                    :fixed="isFrozen(node.field.field_name) ? 'left' : undefined">
          <template #header><FieldHeader :field="node.field" :view="view" @menu="(e) => $emit('field-menu', node.field, e)" /></template>
          <template #default="{ row }"><CellSlot :row="row" :field="node.field" /></template>
        </vxe-column>
      </template>

      <!-- 末尾「+」添加列 -->
      <vxe-column width="48" fixed="right">
        <template #header>
          <span class="add-col" title="添加一列" @click.stop="$emit('add-field')">＋</span>
        </template>
        <template #default><span /></template>
      </vxe-column>
    </vxe-table>
  </div>
</template>

<script setup>
import { computed, h, nextTick, onBeforeUnmount, ref } from 'vue'
import SmartCell from './SmartCell.vue'
import SmartCellEditor from './SmartCellEditor.vue'
import SelectCellPanel from './SelectCellPanel.vue'
import FieldHeader from './FieldHeader.vue'
import { regOf, sortDirectionLabels } from '../../../smart/registry/fieldRegistry.js'
import { evalFillRules } from '../../../smart/utils/format.js'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },        // grid 接口行序列（可能含 __rowType:'group'）
  grouped: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
  aggregations: { type: Object, default: () => ({}) },
  view: { type: Object, default: () => ({ config: {} }) },
  columnGroups: { type: Array, default: () => [] },
  height: { type: [Number, String], default: 480 },
  collapsedGroups: { type: Object, default: () => new Set() },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['cell-commit', 'add-row', 'cell-menu', 'field-menu', 'toggle-group',
                          'selection-change', 'open-config', 'agg-change', 'add-option'])

const gridRef = ref(null)
const editingCell = ref(null)   // {key, fieldName}

const viewConfig = computed(() => props.view?.config || {})
const rowHeightPx = computed(() => ({ default: 36, medium: 52, tall: 76, extraTall: 100 }[viewConfig.value.rowHeight] || 36))
const colWidths = computed(() => viewConfig.value.colWidths || {})
const fillRules = computed(() => viewConfig.value.fillRules || [])

// 视图配置应用：显隐 + 列序
const visibleFields = computed(() => {
  const vis = viewConfig.value.fieldVisibility || {}
  let fs = props.fields.filter(f => vis[f.field_name] !== false)
  const order = viewConfig.value.fieldOrder
  if (order?.length) {
    const idx = new Map(order.map((n, i) => [n, i]))
    fs = [...fs].sort((a, b) => (idx.get(a.field_name) ?? 999) - (idx.get(b.field_name) ?? 999))
  }
  return fs
})

// 两级表头：编组节点 + 散列字段（保持相对顺序，编组内字段聚合到组下）
const headerTree = computed(() => {
  const groups = props.columnGroups.filter(g => (g.field_names || []).length)
  const inGroup = new Set(groups.flatMap(g => g.field_names))
  const nodes = []
  const emittedGroups = new Set()
  for (const f of visibleFields.value) {
    const g = groups.find(x => x.field_names.includes(f.field_name))
    if (!g) {
      nodes.push({ key: f.field_name, isGroup: false, field: f })
    } else if (!emittedGroups.has(g.id)) {
      emittedGroups.add(g.id)
      nodes.push({ key: `g_${g.id}`, isGroup: true, name: g.name,
                   fields: visibleFields.value.filter(x => g.field_names.includes(x.field_name)) })
    }
  }
  return nodes
})

const isFrozen = (name) => {
  const fz = viewConfig.value.frozenFieldId
  if (!fz) return false
  const list = visibleFields.value.map(f => f.field_name)
  const idx = list.indexOf(fz)
  const mine = list.indexOf(name)
  return idx >= 0 && mine >= 0 && mine <= idx
}

// 行序列：折叠分组过滤 + 树形缩进标记 + 行号 + 末尾加行
const gridRows = computed(() => {
  const out = []
  let no = 0
  const hiddenUnder = []   // 折叠组的 key 前缀栈
  const idDepth = new Map()   // 树形：记录 id → 深度
  for (const r of props.rows) {
    if (r.__rowType === 'group') {
      while (hiddenUnder.length && r.depth <= hiddenUnder[hiddenUnder.length - 1].depth) hiddenUnder.pop()
      if (hiddenUnder.length) continue
      out.push({ ...r, __key: r.key })
      if (props.collapsedGroups.has(r.key)) hiddenUnder.push(r)
      continue
    }
    if (hiddenUnder.length) continue
    no += 1
    let depth = 0
    if (r.parent_id != null) depth = (idDepth.get(r.parent_id) ?? 0) + 1
    idDepth.set(r.id, depth)
    out.push({ ...r, __key: `r_${r.id}`, __no: no, __indent: depth })
  }
  out.push({ __rowType: 'add', __key: '__add__' })
  return out
})

const rowClass = ({ row }) => {
  if (row.__rowType === 'group') return `row-group depth-${row.depth}`
  if (row.__rowType === 'add') return 'row-add'
  return ''
}

function cellClass({ row, column }) {
  const cls = []
  if (row.__rowType !== 'add' && row.__rowType !== 'group' && row.__indent > 0 && column.field === visibleFields.value[0]?.field_name) {
    cls.push('cell-indent')
  }
  // 单击选中态（企微式：边框与单元格同大，与编辑态边框同款）
  if (selectedCell.value && row.__key === selectedCell.value.key && column.field === selectedCell.value.fieldName) {
    cls.push('cell-selected')
  }
  // 编辑态：去单元格内边距，编辑器与单元格严格同边界
  if (editingCell.value && row.__key === editingCell.value.key && column.field === editingCell.value.fieldName) {
    cls.push('cell-editing')
  }
  return cls.join(' ')
}

// 单元格渲染（含填色命中 + 编辑态分发）
function CellSlot(props2) {
  const { row, field } = props2
  if (row.__rowType === 'add') {
    return h('span', {
      class: 'add-row-cell',
      onClick: (e) => { e.stopPropagation(); emit('add-row') },
    }, field.field_name === visibleFields.value[0]?.field_name ? '＋ 添加' : '')
  }
  if (row.__rowType === 'group') {
    if (field.field_name !== visibleFields.value[0]?.field_name) {
      const agg = row.aggs?.[field.field_name]
      return h('span', { class: 'group-agg' }, agg != null ? `求和 ${fmtAgg(agg)}` : '')
    }
    return h('span', { class: 'group-head' }, `${groupLabel(row)}（记录数 ${row.count}）`)
  }
  const isEdit = editingCell.value && editingCell.value.key === row.__key && editingCell.value.fieldName === field.field_name
  if (isEdit && !props.readonly) {
    return h(SmartCellEditor, {
      field, record: row,
      frozen: isFrozen(field.field_name),   // 编辑器按 wrapper 判断自己是不是显示副本用
      onCommit: (v) => { editingCell.value = null; emit('cell-commit', { row, field, value: v }) },
      onCancel: () => { editingCell.value = null },
      'onOpen-config': (f) => emit('open-config', f),
      // 单元格内新建选项：父级落库为真选项后提交新 optionId（编辑器即关闭）
      'onAdd-option': (label) => { editingCell.value = null; emit('add-option', { row, field, label }) },
    })
  }
  // 单选/多选单击选中：呈现编辑态锚点（标签+✕+下拉按钮），面板不展开；
  // 点下拉按钮或双击锚点 → open 进编辑态（面板展开）
  const isSelEnum = selectedCell.value && selectedCell.value.key === row.__key
    && selectedCell.value.fieldName === field.field_name
    && ['singleSelect', 'multiSelect'].includes(field.field_type)
  if (isSelEnum) {
    return h(SelectCellPanel, {
      field, record: row, frozen: isFrozen(field.field_name), closed: true,
      onCommit: (v) => emit('cell-commit', { row, field, value: v }),   // ✕ 清除直接生效
      onOpen: () => {
        if (props.readonly) return
        selectedCell.value = null
        editingCell.value = { key: row.__key, fieldName: field.field_name }
      },
    })
  }
  // 文本单元格单击选中：用与编辑相同的浮层只读展示全文；双击浮层（enter-edit）再进编辑
  const isSelText = selectedCell.value && selectedCell.value.key === row.__key
    && selectedCell.value.fieldName === field.field_name && field.field_type === 'text'
  if (isSelText) {
    return h(SmartCellEditor, {
      field, record: row, frozen: isFrozen(field.field_name), preview: true,
      onCancel: () => { selectedCell.value = null },
      'onEnter-edit': () => {
        if (props.readonly) return
        selectedCell.value = null
        editingCell.value = { key: row.__key, fieldName: field.field_name }
      },
    })
  }
  const fill = evalFillRules(fillRules.value, field, row[field.field_name])
  return h(SmartCell, { field, record: row, fillColor: fill })
}

function groupLabel(row) {
  const f = props.fields.find(x => x.field_name === row.fieldId)
  const v = row.value
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return `${f?.label || ''}: 空`
  if (f?.field_type === 'singleSelect' || f?.field_type === 'multiSelect') {
    const opts = f.options?.options || []
    const ids = Array.isArray(v) ? v : [v]
    return ids.map(id => opts.find(o => o.id === id)?.label ?? id).join('、')
  }
  return `${f?.label}: ${v}`
}

function fmtAgg(v) {
  return typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(2) : v
}

const IMMEDIATE = ['checkbox']
const selectedCell = ref(null)   // 单击选中态 {key, fieldName}（企微式：单击选中、双击编辑）

function onCellClick({ row, column }) {
  if (props.readonly) return
  if (!row || row.__rowType === 'add') return
  if (row.__rowType === 'group') return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return
  if (IMMEDIATE.includes(f.field_type)) {
    emit('cell-commit', { row, field: f, value: !row[f.field_name] })
    return
  }
  // 单击只做选中（重复点同一格也保持选中态），进入编辑只能通过双击
  selectedCell.value = { key: row.__key, fieldName: f.field_name }
}

function onCellDblClick({ row, column }) {
  if (props.readonly) return
  if (!row || row.__rowType === 'add' || row.__rowType === 'group') return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f || IMMEDIATE.includes(f.field_type)) return   // checkbox 单击已切换，无需编辑态
  selectedCell.value = null   // 编辑态即脱离选中态
  editingCell.value = { key: row.__key, fieldName: f.field_name }
}

// Esc 取消选中（编辑态的 Esc 由编辑器自身处理）
function onDocKeydown(e) {
  if (e.key === 'Escape' && selectedCell.value && !editingCell.value) {
    selectedCell.value = null
    // vxe 的 cell-class-name 只在渲染周期重算：Esc 清选中不走数据流，手动触发列重渲染
    gridRef.value?.refreshColumn?.()
  }
}

// vxe 原生右键菜单（menu-config；cell-contextmenu 事件在 v4 不对外暴露）
const menuConfig = computed(() => ({
  body: {
    options: [[
      { code: 'expand', name: '↗ 展开记录' },
      { code: 'only', name: '⧩ 只看此内容' },
      { code: 'exclude', name: '⧩ 不看此内容' },
      { code: 'duplicate', name: '⧉ 创建副本' },
      { code: 'add-child', name: '⤦ 添加子记录' },
      { code: 'delete', name: '🗑 删除', className: 'ctx-danger' },
    ]],
    visibleMethod: ({ row }) => !!row && !row.__rowType,   // 组标题行/加行不出菜单
  },
}))

function onMenuClick({ row, column, menu }) {
  if (!row || row.__rowType || !menu) return
  const f = props.fields.find(x => x.field_name === column.field)
  emit('cell-menu', { row, field: f, cmd: menu.code })
}

function onCheckAll({ checked }) { emit('selection-change', checked ? dataRowSelection() : []) }
function onCheckChange() { emit('selection-change', dataRowSelection()) }
function dataRowSelection() {
  const recs = gridRef.value?.getCheckboxRecords?.() || []
  return recs.filter(r => !r.__rowType)
}

// 汇总行：首字段列「记录数 N」，各列按 aggregations 渲染，可点击切换聚合方式
function footerMethod({ columns }) {
  const firstField = visibleFields.value[0]?.field_name
  return [
    columns.map((col) => {
      if (col.field === firstField) return `记录数 ${props.total}`
      const f = props.fields.find(x => x.field_name === col.field)
      if (f && props.aggregations[f.field_name] != null) return `求和 ${fmtAgg(props.aggregations[f.field_name])}`
      return ''
    }),
  ]
}

onBeforeUnmount(() => document.removeEventListener('keydown', onDocKeydown))

document.addEventListener('keydown', onDocKeydown)

defineExpose({ clearEditing: () => { editingCell.value = null; selectedCell.value = null } })
</script>

<style scoped>
.smart-grid { width: 100%; }
.add-col { color: var(--el-color-primary); font-weight: 600; cursor: pointer; font-size: 15px; }
.add-row-cell { color: var(--el-color-primary); cursor: pointer; font-size: 13px; }
.group-toggle { cursor: pointer; color: var(--el-text-color-secondary); user-select: none; }
.row-no { color: var(--el-text-color-placeholder); font-size: 12px; }
.group-head { font-weight: 600; font-size: 13px; }
.group-agg { font-size: 12px; color: var(--el-text-color-secondary); }
.smart-vxe :deep(.row-group) { background: #fffbe6; }
.smart-vxe :deep(.row-group.depth-1) { background: #fffdf0; }
.smart-vxe :deep(.row-group.depth-2) { background: #fffef7; }
.smart-vxe :deep(.row-add) { background: var(--el-fill-color-lighter); }
.smart-vxe :deep(.vxe-body--column.col-no) { color: var(--el-text-color-placeholder); font-size: 18px; }
/* 单击选中态：2px 主色边框（inset 阴影实现，与单元格同大、不占布局），与编辑态边框同款 */
.smart-vxe :deep(.vxe-body--column.cell-selected) { box-shadow: 0 0 0 2px var(--el-color-primary) inset; position: relative; z-index: 1; }
/* 编辑态：去内边距，编辑器严格填满单元格。编辑边框画在 .vxe-cell 上（它与 td 严格同盒），
   不能画在 el-input__wrapper 上——EP wrapper 是 content-box，height:100%+padding 会高出 2px
   被 .vxe-cell 的 overflow:hidden 各裁 1px（上下边框变细的原因） */
.smart-vxe :deep(.vxe-body--column.cell-editing .vxe-cell) {
  padding: 0; height: 100%; box-shadow: 0 0 0 2px var(--el-color-primary) inset;
}
.smart-vxe :deep(.vxe-body--column.cell-editing .vxe-cell--wrapper) { height: 100%; }
.smart-vxe :deep(.vxe-body--column.cell-editing .el-input),
.smart-vxe :deep(.vxe-body--column.cell-editing .el-select),
.smart-vxe :deep(.vxe-body--column.cell-editing .el-date-editor.el-input) { width: 100%; height: 100%; }
.smart-vxe :deep(.vxe-body--column.cell-editing .el-input__wrapper),
.smart-vxe :deep(.vxe-body--column.cell-editing .el-select__wrapper) {
  height: 100%; min-height: 0; border-radius: 0; box-sizing: border-box;
  box-shadow: none; background: transparent;   /* 透出 .vxe-cell 上的编辑态边框 */
}
.smart-vxe :deep(.vxe-body--column.cell-editing .el-input__inner) { height: 100%; }
.smart-vxe :deep(.cell-indent) { padding-left: 18px; }
/* 显示态内容整体上移 1px：13px CJK 文字在 36px 行高内半行距分布偏下，光学居中补偿。
   只作用非编辑态——编辑边框画在 .vxe-cell 上、编辑器严格填满单元格，不能跟着移 */
.smart-vxe :deep(.vxe-body--column:not(.cell-editing) .vxe-cell--wrapper) { transform: translateY(-2px); }
/* 查看/选中态禁止选中文字（企微式：单击只是选中单元格，双击才进编辑态，编辑器内不受影响） */
.smart-vxe :deep(.vxe-body--column:not(.cell-editing) .vxe-cell) { user-select: none; }
/* 行选 checkbox（设计稿 PixPin_2026-10-15_00-02-56 风格：细边圆角小方框；选中主色底+白勾） */
.smart-vxe :deep(.vxe-checkbox--icon) {
  font-size: 0;   /* 隐藏 vxe 图标字体的字形，自绘方框 */
  display: inline-block;   /* inline 元素不吃 width/height，必须转 inline-block */
  vertical-align: middle;
  width: 15px; height: 15px; box-sizing: border-box; position: relative;
  border: 1px solid var(--el-border-color-dark); border-radius: 3px; background: #fff;
  transition: background-color .15s, border-color .15s;
}
.smart-vxe :deep(.vxe-cell--checkbox:hover .vxe-checkbox--icon) { border-color: var(--el-color-primary); }
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked-fill),
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked),
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate-fill),
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate) {
  background: var(--el-color-primary); border-color: var(--el-color-primary);
}
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked-fill)::after,
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked)::after {
  content: ''; position: absolute; left: 4px; top: 1px; width: 4px; height: 8px;
  border: solid #fff; border-width: 0 1.6px 1.6px 0; transform: rotate(45deg);
}
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate-fill)::after,
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate)::after {
  content: ''; position: absolute; left: 3px; top: 6px; width: 7px; height: 1.6px; background: #fff;
}
/* 表头单元格统一灰色（含 # 列；字段名/图标的样式由 FieldHeader 自己管，这里不覆盖避免优先级打架） */
.smart-vxe :deep(.vxe-header--column) { font-size: 13px; color: var(--el-text-color-secondary); }
:deep(.field-head) { display: inline-flex; align-items: center; gap: 4px; width: 100%; cursor: default; }
:deep(.filter-dot) { color: var(--el-color-primary); }
:deep(.sort-mark) { color: var(--el-color-primary); }
:deep(.head-menu) { margin-left: auto; color: var(--el-text-color-placeholder); padding: 0 2px; cursor: pointer; }
:deep(.head-menu:hover) { color: var(--el-color-primary); }
</style>
