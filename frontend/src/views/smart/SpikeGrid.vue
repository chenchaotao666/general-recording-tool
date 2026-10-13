<template>
  <div class="spike-page">
    <div class="page-header">
      <div>
        <h3>vxe-table Spike（智能表网格验证）</h3>
        <p class="hint">
          验证项：冻结列（行号+首列）｜ 行高四档 ｜ 单元格内联编辑（文本/单选/复选框）｜ 汇总行 ｜ 5000 行虚拟滚动
        </p>
      </div>
      <div class="ops">
        <el-radio-group v-model="rowHeight" size="small">
          <el-radio-button value="default">默认</el-radio-button>
          <el-radio-button value="medium">中等</el-radio-button>
          <el-radio-button value="tall">高</el-radio-button>
          <el-radio-button value="extraTall">超高</el-radio-button>
        </el-radio-group>
        <el-checkbox v-model="frozen" size="small">冻结首列</el-checkbox>
        <el-button size="small" @click="addRow">＋ 添加一行</el-button>
        <span class="hint">改动 {{ changes }} 次</span>
      </div>
    </div>

    <SmartGrid
      :fields="fields" :rows="rows" :total="rows.length"
      :aggregations="aggs" :row-height="rowHeight"
      :frozen-field-id="frozen ? 'f_1' : null"
      :height="gridHeight"
      @cell-commit="onCommit" @add-row="addRow"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import SmartGrid from '../../components/smart/grid/SmartGrid.vue'

const rowHeight = ref('default')
const frozen = ref(true)
const changes = ref(0)

const fields = [
  { field_name: 'f_1', label: '文本', field_type: 'text', options: {} },
  { field_name: 'f_2', label: '单选', field_type: 'singleSelect', options: { options: [
    { id: 'opt_1', label: '选项1', color: 'blue' },
    { id: 'opt_2', label: '选项2', color: 'green' },
    { id: 'opt_3', label: '选项3', color: 'orange' },
  ] } },
  { field_name: 'f_3', label: '人员', field_type: 'member', options: { multiple: true } },
  { field_name: 'f_4', label: '数字', field_type: 'number', options: { thousandSeparator: true } },
  { field_name: 'f_5', label: '货币', field_type: 'currency', options: { currencyCode: 'CNY', currencySymbol: '￥', precision: 2, thousandSeparator: true } },
  { field_name: 'f_6', label: '日期', field_type: 'date', options: { format: 'yyyy-MM-dd' } },
  { field_name: 'f_7', label: '复选框', field_type: 'checkbox', options: {} },
  { field_name: 'f_8', label: '链接', field_type: 'url', options: {} },
  { field_name: 'f_9', label: '电话', field_type: 'phone', options: {} },
  { field_name: 'f_10', label: '百分数', field_type: 'percent', options: {} },
]

// 5000 行 mock
const rows = reactive(Array.from({ length: 5000 }, (_, i) => ({
  id: i + 1,
  f_1: `记录-${String(i + 1).padStart(4, '0')}`,
  f_2: ['opt_1', 'opt_2', 'opt_3'][i % 3],
  f_3: [1, 2],
  f_4: (i * 37) % 100000,
  f_5: (i * 13.7) % 50000,
  f_6: '2026-10-13 10:00:00',
  f_7: i % 2 === 0,
  f_8: { url: 'https://example.com', text: '示例链接' },
  f_9: '13800138000',
  f_10: i % 100,
})))

const aggs = computed(() => ({ f_4: rows.reduce((s, r) => s + (r.f_4 || 0), 0) }))

const gridHeight = computed(() => window.innerHeight - 180)

function onCommit({ rowId, field, value }) {
  const row = rows.find(r => r.id === rowId)
  if (row) {
    row[field.field_name] = value
    changes.value++
  }
}

let addSeq = rows.length + 1
function addRow() {
  rows.unshift({ id: addSeq++ })   // 顶部插入（设计文档 §7.1）
  ElMessage.success('已在顶部添加一行')
}
</script>

<style scoped>
.spike-page { padding: 16px 20px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px; }
.page-header h3 { margin: 0 0 4px; }
.hint { color: #909399; font-size: 12px; margin: 0; }
.ops { display: flex; align-items: center; gap: 16px; }
</style>
