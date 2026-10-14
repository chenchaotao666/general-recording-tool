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
import { computed, h, onBeforeUnmount, ref } from 'vue'
import SmartCell from './SmartCell.vue'
import SmartCellEditor from './SmartCellEditor.vue'
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
                          'selection-change', 'open-config', 'agg-change'])

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
      onCommit: (v) => { editingCell.value = null; emit('cell-commit', { row, field, value: v }) },
      onCancel: () => { editingCell.value = null },
      'onOpen-config': (f) => emit('open-config', f),
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
let selectTimer = null           // 选中态延迟落地：双击时取消，避免"选中框闪现→编辑器"的中间态

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
  // 已选中的单元格再点一次 = 进入编辑（企微一致）
  if (selectedCell.value?.key === row.__key && selectedCell.value?.fieldName === f.field_name) {
    clearTimeout(selectTimer)
    selectTimer = null
    selectedCell.value = null
    editingCell.value = { key: row.__key, fieldName: f.field_name }
  } else {
    // 延迟 ~200ms 落选中框：若紧随其后的第二击（双击）到来，则跳过选中直接进编辑
    const target = { key: row.__key, fieldName: f.field_name }
    clearTimeout(selectTimer)
    selectTimer = setTimeout(() => {
      selectedCell.value = target
      selectTimer = null
    }, 200)
  }
}

function onCellDblClick({ row, column }) {
  if (props.readonly) return
  if (!row || row.__rowType === 'add' || row.__rowType === 'group') return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f || IMMEDIATE.includes(f.field_type)) return   // checkbox 单击已切换，无需编辑态
  clearTimeout(selectTimer)   // 双击路径不出现选中态
  selectTimer = null
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

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onDocKeydown)
  clearTimeout(selectTimer)
})

document.addEventListener('keydown', onDocKeydown)

defineExpose({ clearEditing: () => {
  clearTimeout(selectTimer)
  selectTimer = null
  editingCell.value = null
  selectedCell.value = null
} })
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
.smart-vxe :deep(.vxe-body--column.col-no) { color: var(--el-text-color-placeholder); font-size: 12px; }
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
:deep(.field-head) { display: inline-flex; align-items: center; gap: 4px; width: 100%; cursor: default; }
:deep(.field-icon) { color: var(--el-color-primary); font-size: 12px; min-width: 16px; text-align: center; }
:deep(.field-name) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.filter-dot) { color: var(--el-color-primary); }
:deep(.sort-mark) { color: var(--el-color-primary); }
:deep(.head-menu) { margin-left: auto; color: var(--el-text-color-placeholder); padding: 0 2px; cursor: pointer; }
:deep(.head-menu:hover) { color: var(--el-color-primary); }
</style>
