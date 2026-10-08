<template>
  <el-dialog
    :model-value="modelValue" title="打印" width="720px" destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading">
      <div class="picker-head">
        <div class="picker-opts">
          <el-radio-group v-model="paper" size="small">
            <el-radio-button value="a4">A4</el-radio-button>
            <el-radio-button value="half">2等分</el-radio-button>
            <el-radio-button value="third">3等分</el-radio-button>
          </el-radio-group>
          <span class="muted">按当前筛选结果填充（{{ total }} 条{{ total > 200 ? '，超出上限仅前 200 条' : '' }}）明细记录</span>
        </div>
        <el-button v-if="canManage" type="primary" plain size="small" :icon="Plus" @click="$emit('design', null)">
          新建模板
        </el-button>
      </div>

      <!-- 与数据表主列表同风格：border + stripe + 默认行高，全系统统一 -->
      <el-table
        :data="pagedTemplates" border stripe max-height="380" class="tpl-table"
        :row-class-name="rowClass"
      >
        <el-table-column type="index" width="55" label="#" />
        <el-table-column prop="name" label="模板名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.name }}
            <el-tag v-if="row.id === lastId" size="small" type="warning" effect="plain" class="last-tag">上次使用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" :width="canManage ? 340 : 180" align="right" class-name="ops-col">
          <template #default="{ row }">
            <el-button type="primary" plain size="small" :disabled="!row.has_excel" @click="onPreview(row)">预览</el-button>
            <el-button type="primary" size="small" class="print-btn" :disabled="!row.has_excel" @click="onPrint(row)">打印</el-button>
            <template v-if="canManage">
              <el-button text type="primary" size="small" @click="$emit('design', row.id)">编辑</el-button>
              <el-button text type="primary" size="small" @click="onDuplicate(row)">复制</el-button>
              <el-popconfirm title="确定删除该模板？" width="220" @confirm="onDelete(row)">
                <template #reference>
                  <el-button text type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无模板，点右上角「新建模板」" :image-size="60" />
        </template>
      </el-table>

      <!-- 与数据表同款分页（前端切片；总数即模板数） -->
      <el-pagination
        v-model:current-page="tplPage" v-model:page-size="tplPageSize"
        :total="templates.length" layout="total, sizes, prev, pager, next"
        style="margin-top: 14px"
      />
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { deletePrintTemplate, duplicatePrintTemplate, listPrintTemplates } from '../api'
import { getLastTpl, getPaper, setLastTpl, setPaper } from '../utils/printPrefs'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tableId: { type: Number, required: true },
  total: { type: Number, default: 0 },   // 当前筛选结果条数（批量打印提示）
})
const emit = defineEmits(['update:modelValue', 'preview', 'print', 'design'])

const loading = ref(false)
const templates = ref([])
const canManage = ref(false)
const lastId = ref(null)                 // 上次使用的模板（本表，localStorage）
const paper = ref(getPaper())            // 纸张偏好全局共享，预览/直接打印同口径

watch(paper, (v) => setPaper(v))

// 上次使用的模板置顶，其余保持后端顺序
const sortedTemplates = computed(() => {
  if (!lastId.value) return templates.value
  const i = templates.value.findIndex((t) => t.id === lastId.value)
  if (i <= 0) return templates.value
  return [templates.value[i], ...templates.value.slice(0, i), ...templates.value.slice(i + 1)]
})

const rowClass = ({ row }) => (row.id === lastId.value ? 'row-last' : '')

// 前端分页（模板全量已在内存，切片即可；样式与数据表主列表一致）
const tplPage = ref(1)
const tplPageSize = ref(10)
const pagedTemplates = computed(() => {
  const start = (tplPage.value - 1) * tplPageSize.value
  return sortedTemplates.value.slice(start, start + tplPageSize.value)
})

async function reload() {
  loading.value = true
  try {
    const res = await listPrintTemplates(props.tableId)
    templates.value = res.templates || []
    canManage.value = !!res.can_manage
    lastId.value = getLastTpl(props.tableId)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (v) => v && reload())

// 设计器保存后由父组件调用：刷新列表
defineExpose({ reload })

function _markUsed(row) {
  lastId.value = row.id
  setLastTpl(props.tableId, row.id)
}

function onPreview(row) {
  if (!row.has_excel) return
  _markUsed(row)
  emit('preview', row)
}

function onPrint(row) {
  if (!row.has_excel) return
  _markUsed(row)
  emit('print', row)
}

async function onDuplicate(t) {
  try {
    await duplicatePrintTemplate(t.id)
    ElMessage.success(`已复制为「${t.name}（副本）」`)
    await reload()
  } catch (e) { ElMessage.error(e.message) }
}

async function onDelete(t) {
  try {
    await deletePrintTemplate(t.id)
    await reload()
  } catch (e) { ElMessage.error(e.message) }
}
</script>

<style scoped>
.picker-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 12px; flex-wrap: wrap; }
.tpl-table { width: 100%; }
/* 操作列：flex 统一按钮间距（预览/打印是普通按钮、编辑/复制/删除是文字按钮且删除套了
   popconfirm，默认的 el-button+el-button 边距规则管不到所有组合，导致间距不一致）。
   font-size:0 消除按钮间模板换行产生的空白文本节点（v-if/popconfirm 边界没有空白，
   其余对有，不加这个还是会有的挤有的宽）；el-button 自带字号，不受影响。
   注意 class-name 会同时加到表头，必须限定 .el-table__body，否则表头「操作」也被隐藏 */
.tpl-table :deep(.el-table__body .ops-col .cell) { display: flex; align-items: center; justify-content: flex-end; gap: 6px; font-size: 0; }
.tpl-table :deep(.el-table__body .ops-col .el-button),
.tpl-table :deep(.el-table__body .ops-col .el-button + .el-button) { margin-left: 0; }
/* 「打印」是主操作，与「预览」拉开一点（6px gap + 10px = 16px） */
.tpl-table :deep(.el-table__body .ops-col .print-btn) { margin-left: 10px; }
.tpl-table :deep(.row-last) { background: #fdf6ec; }
.last-tag { margin-left: 6px; }
.picker-opts { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.picker-opts .muted { color: #909399; font-size: 12px; }
</style>
