<template>
  <div class="subform-field">
    <el-table :data="rows" border size="small" show-summary :summary-method="summaryMethod" max-height="320">
      <el-table-column type="index" width="46" label="#" align="center" />
      <el-table-column
        v-for="c in columns" :key="c.field_name" :prop="c.field_name" :label="c.label"
        min-width="100" show-overflow-tooltip
      >
        <template #default="{ row }">{{ fmtCell(c, row[c.field_name]) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right" align="center">
        <template #default="{ $index }">
          <el-button text type="primary" size="small" @click="openRow($index)">编辑</el-button>
          <el-button text type="danger" size="small" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无明细，点击下方按钮添加</template>
    </el-table>
    <el-button style="margin-top: 8px" type="primary" plain size="small" :icon="Plus" @click="openRow(-1)">
      添加明细
    </el-button>

    <!-- 行编辑弹窗：复用 DynamicForm（关联带出/公式/校验自动生效） -->
    <el-dialog
      v-model="rowDialogVisible" :title="editingIndex >= 0 ? '编辑明细' : '添加明细'"
      width="560px" destroy-on-close append-to-body
    >
      <DynamicForm
        v-if="rowDialogVisible"
        :fields="columns" :initial="editingIndex >= 0 ? rows[editingIndex] : {}"
        @submit="onRowSubmit" @cancel="rowDialogVisible = false"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import DynamicForm from './DynamicForm.vue'

// 子表控件：只读明细表格 + 弹窗行编辑。值为行对象数组（v-model）。
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },   // field.options.columns（不允许嵌套 subform）
})
const emit = defineEmits(['update:modelValue', 'change'])

const rows = computed(() => (Array.isArray(props.modelValue) ? props.modelValue : []))

const rowDialogVisible = ref(false)
const editingIndex = ref(-1)

function fmtCell(c, v) {
  if (v === null || v === undefined || v === '') return ''
  if (c.data_type === 'bool') return v ? '是' : '否'
  if (c.data_type === 'date') return String(v).slice(0, 10)
  if (c.data_type === 'datetime') return String(v).replace('T', ' ').slice(0, 19)
  if (c.data_type === 'image') return `共 ${Array.isArray(v) ? v.length : 0} 张`
  return v
}

// 合计行：仅数值列（int/decimal）求和
function summaryMethod({ columns: cols, data }) {
  return cols.map((col, i) => {
    if (i === 0) return '合计'
    const c = columns.find((x) => x.field_name === col.property)
    if (!c || !['int', 'decimal'].includes(c.data_type)) return ''
    const sum = data.reduce((acc, row) => {
      const v = parseFloat(row[c.field_name])
      return Number.isFinite(v) ? acc + v : acc
    }, 0)
    return sum ? Math.round(sum * 10000) / 10000 : ''
  })
}

function openRow(index) {
  editingIndex.value = index
  rowDialogVisible.value = true
}

function onRowSubmit(values) {
  const next = rows.value.slice()
  if (editingIndex.value >= 0) next.splice(editingIndex.value, 1, values)
  else next.push(values)
  emit('update:modelValue', next)
  emit('change', next)
  rowDialogVisible.value = false
}

function removeRow(index) {
  const next = rows.value.slice()
  next.splice(index, 1)
  emit('update:modelValue', next)
  emit('change', next)
}
</script>
