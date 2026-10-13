<template>
  <!-- SmartGrid 雏形（V1 spike）：vxe-table 封装——冻结列/行高/虚拟滚动/汇总行/单元格编辑状态机。
       flatten 行序列：数据行 + 末尾 {__rowType:'add'} 加行（V2 分组横幅行同机制扩展）。 -->
  <div class="smart-grid">
    <vxe-table
      ref="gridRef"
      class="smart-vxe"
      :data="gridRows"
      :height="height"
      border
      :row-config="{ height: rowHeightPx, isHover: true }"
      :column-config="{ resizable: true }"
      :scroll-y="{ enabled: true, gt: 100 }"
      :scroll-x="{ enabled: true, gt: 20 }"
      :show-footer="true"
      :footer-method="footerMethod"
      :cell-class-name="cellClass"
      @cell-click="onCellClick"
    >
      <!-- 行号 + 多选列（冻结） -->
      <vxe-column type="checkbox" width="36" fixed="left" class-name="col-check" />
      <vxe-column width="46" fixed="left" title="#" :formatter="rowNoFormatter" class-name="col-no" />

      <!-- 字段列 -->
      <vxe-column
        v-for="f in visibleFields" :key="f.field_name"
        :field="f.field_name" :title="f.label"
        :width="colWidths[f.field_name] || 160"
        :fixed="isFrozen(f.field_name) ? 'left' : undefined"
      >
        <template #header>
          <span class="field-head">
            <span class="field-icon">{{ typeIcon(f) }}</span>{{ f.label }}
          </span>
        </template>
        <template #default="{ row, column }">
          <span v-if="row.__rowType === 'add'" class="add-row-cell">
            <template v-if="column.field === visibleFields[0]?.field_name">＋ 添加</template>
          </span>
          <template v-else>
            <!-- 编辑态：内联替换；展示态：SmartCell 分发 -->
            <SmartCellEditor
              v-if="isEditing(row, f)"
              :field="f" :record="row"
              @commit="(v) => onCommit(row, f, v)"
              @cancel="editingCell = null"
            />
            <SmartCell v-else :field="f" :record="row" />
          </template>
        </template>
      </vxe-column>

      <!-- 末尾「+」添加列占位 -->
      <vxe-column width="48" fixed="right" title="">
        <template #header><span class="add-col">＋</span></template>
        <template #default><span /></template>
      </vxe-column>
    </vxe-table>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import SmartCell from './SmartCell.vue'
import SmartCellEditor from './SmartCellEditor.vue'

const props = defineProps({
  fields: { type: Array, default: () => [] },        // [{field_name,label,field_type,options}]
  rows: { type: Array, default: () => [] },          // 当前页记录
  total: { type: Number, default: 0 },
  aggregations: { type: Object, default: () => ({}) },
  rowHeight: { type: String, default: 'default' },   // default|medium|tall|extraTall
  frozenFieldId: { type: String, default: null },
  colWidths: { type: Object, default: () => ({}) },
  fieldVisibility: { type: Object, default: () => ({}) },
  fieldOrder: { type: Array, default: null },
  height: { type: [Number, String], default: 480 },
})
const emit = defineEmits(['cell-commit', 'add-row'])

const HEIGHTS = { default: 36, medium: 52, tall: 76, extraTall: 100 }
const rowHeightPx = computed(() => HEIGHTS[props.rowHeight] || 36)

const gridRef = ref(null)
const editingCell = ref(null)   // {rowId, fieldName}

// flatten 行序列：数据行 + 末尾加行
const gridRows = computed(() => [...props.rows, { __rowType: 'add', id: '__add__' }])

// 视图配置应用：显隐 + 顺序（纯前端，数据层不动）
const visibleFields = computed(() => {
  let fs = props.fields.filter(f => props.fieldVisibility[f.field_name] !== false)
  if (props.fieldOrder?.length) {
    const idx = new Map(props.fieldOrder.map((n, i) => [n, i]))
    fs = [...fs].sort((a, b) => (idx.get(a.field_name) ?? 999) - (idx.get(b.field_name) ?? 999))
  }
  return fs
})

const isFrozen = (name) => {
  if (!props.frozenFieldId) return false
  const idx = visibleFields.value.findIndex(f => f.field_name === props.frozenFieldId)
  const mine = visibleFields.value.findIndex(f => f.field_name === name)
  return idx >= 0 && mine >= 0 && mine <= idx
}

const isEditing = (row, f) =>
  editingCell.value && editingCell.value.rowId === row.id && editingCell.value.fieldName === f.field_name

const IMMEDIATE_TYPES = ['checkbox']   // A 类：单击即提交

function onCellClick({ row, column }) {
  if (!row || row.__rowType === 'add') {
    if (row?.__rowType === 'add') emit('add-row')
    return
  }
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return
  if (IMMEDIATE_TYPES.includes(f.field_type)) {
    emit('cell-commit', { rowId: row.id, field: f, value: !row[f.field_name] })
    return
  }
  editingCell.value = { rowId: row.id, fieldName: f.field_name }
}

function onCommit(row, f, value) {
  editingCell.value = null
  emit('cell-commit', { rowId: row.id, field: f, value })
}

const rowNoFormatter = ({ row, rowIndex }) => (row.__rowType === 'add' ? '' : rowIndex + 1)

const cellClass = ({ row }) => (row.__rowType === 'add' ? 'row-add' : '')

const TYPE_ICONS = {
  text: 'A', singleSelect: '⊙', multiSelect: '☰', number: '₁₂₃', percent: '%',
  currency: '¥', date: '📅', checkbox: '☑', url: '🔗', phone: '📞', email: '✉', member: '👤',
}
const typeIcon = (f) => TYPE_ICONS[f.field_type] || 'A'

// 汇总行：首字段列「记录数」、数值列按 aggregations 渲染
function footerMethod({ columns }) {
  const firstField = visibleFields.value[0]?.field_name
  return [
    columns.map((col) => {
      if (col.field === firstField) return `记录数 ${props.total}`
      const f = props.fields.find(x => x.field_name === col.field)
      if (f && props.aggregations[f.field_name] != null) return `求和 ${props.aggregations[f.field_name]}`
      return ''
    }),
  ]
}
</script>

<style scoped>
.smart-grid { width: 100%; }
.field-head { display: inline-flex; align-items: center; gap: 4px; }
.field-icon { color: var(--el-color-primary); font-size: 12px; width: 16px; text-align: center; }
.add-col { color: var(--el-color-primary); font-weight: 600; cursor: pointer; }
.add-row-cell { color: var(--el-color-primary); cursor: pointer; }
.smart-vxe :deep(.row-add) { background: var(--el-fill-color-lighter); }
.smart-vxe :deep(.vxe-body--column.col-no) { color: var(--el-text-color-placeholder); font-size: 12px; }
</style>
