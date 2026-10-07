<template>
  <el-dialog
    :model-value="modelValue" title="打印" width="720px" destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading">
      <div class="picker-head">
        <span class="picker-title">打印模板（{{ templates.length }}）</span>
        <el-button v-if="canManage" type="primary" plain size="small" :icon="Plus" @click="$emit('design', null)">
          新建模板
        </el-button>
      </div>

      <el-table :data="templates" size="small" max-height="380" class="tpl-table">
        <el-table-column prop="name" label="模板名称" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" :width="canManage ? 300 : 180" align="right">
          <template #default="{ row }">
            <el-button type="primary" plain size="small" :disabled="!row.has_excel" @click="$emit('preview', row)">预览</el-button>
            <el-button type="primary" size="small" :disabled="!row.has_excel" @click="$emit('print', row)">打印</el-button>
            <template v-if="canManage">
              <el-button text type="primary" size="small" @click="$emit('design', row.id)">编辑</el-button>
              <el-popconfirm title="确定删除该模板？" @confirm="onDelete(row)">
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

      <div class="picker-opts">
        <span class="muted">按当前筛选结果填充（{{ total }} 条{{ total > 200 ? '，超出上限仅前 200 条' : '' }}）明细记录</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { deletePrintTemplate, listPrintTemplates } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tableId: { type: Number, required: true },
  total: { type: Number, default: 0 },   // 当前筛选结果条数（批量打印提示）
})
const emit = defineEmits(['update:modelValue', 'preview', 'print', 'design'])

const loading = ref(false)
const templates = ref([])
const canManage = ref(false)

async function reload() {
  loading.value = true
  try {
    const res = await listPrintTemplates(props.tableId)
    templates.value = res.templates || []
    canManage.value = !!res.can_manage
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (v) => v && reload())

// 设计器保存后由父组件调用：刷新列表
defineExpose({ reload })

async function onDelete(t) {
  try {
    await deletePrintTemplate(t.id)
    await reload()
  } catch (e) { ElMessage.error(e.message) }
}
</script>

<style scoped>
.picker-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.picker-title { font-size: 14px; color: #303133; }
.tpl-table { width: 100%; }
.tpl-table :deep(.el-button + .el-button) { margin-left: 6px; }
.picker-opts { display: flex; align-items: center; gap: 16px; margin-top: 10px; flex-wrap: wrap; }
.picker-opts .muted { color: #909399; font-size: 12px; }
</style>
