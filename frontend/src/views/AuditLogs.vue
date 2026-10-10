<template>
  <div>
    <div class="page-header"><h2>审计日志</h2></div>

    <el-form inline class="filter-bar">
      <el-form-item label="数据表">
        <el-select v-model="filters.table_id" clearable filterable placeholder="全部" style="width: 180px">
          <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="操作人">
        <el-input v-model="filters.user" clearable placeholder="用户名" style="width: 130px" />
      </el-form-item>
      <el-form-item label="动作">
        <el-select v-model="filters.action" clearable placeholder="全部" style="width: 130px">
          <el-option v-for="a in actions" :key="a.value" :label="a.label" :value="a.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="时间">
        <el-date-picker
          v-model="range" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始" end-placeholder="结束" style="width: 240px"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="load(1)">查询</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" v-loading="loading" border>
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="user" label="操作人" width="110" />
      <el-table-column label="动作" width="120">
        <template #default="{ row }">{{ actionLabel(row.action) }}</template>
      </el-table-column>
      <el-table-column label="数据表" min-width="140">
        <template #default="{ row }">{{ row.table_label || row.table_id || '—' }}</template>
      </el-table-column>
      <el-table-column prop="record_id" label="记录" width="90">
        <template #default="{ row }">{{ row.record_id ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="变更内容" width="110">
        <template #default="{ row }">
          <el-button v-if="row.before || row.after" link type="primary" size="small" @click="showDiff(row)">查看</el-button>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <template #empty>暂无审计记录</template>
    </el-table>

    <el-pagination
      class="pager" layout="total, prev, pager, next" :total="total"
      :page-size="filters.page_size" :current-page="filters.page"
      @current-change="load"
    />

    <el-dialog v-model="diffVisible" title="变更内容" width="720px">
      <el-row :gutter="12">
        <el-col :span="12">
          <div class="diff-title">变更前</div>
          <pre class="diff-json">{{ pretty(current?.before) }}</pre>
        </el-col>
        <el-col :span="12">
          <div class="diff-title">变更后</div>
          <pre class="diff-json">{{ pretty(current?.after) }}</pre>
        </el-col>
      </el-row>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAuditLogs, listTables } from '../api'

const actions = [
  { value: 'create', label: '新增记录' },
  { value: 'update', label: '修改记录' },
  { value: 'delete', label: '删除记录' },
  { value: 'create_table', label: '建表' },
  { value: 'alter_table', label: '改表结构' },
  { value: 'drop_table', label: '删表' },
  { value: 'import', label: '导入' },
  { value: 'subscription_change', label: '订阅变更' },
  { value: 'plan_entitlements_change', label: '套餐配置变更' },
  { value: 'create_tenant', label: '开租户' },
]
const actionLabel = (a) => actions.find((x) => x.value === a)?.label || a

const items = ref([])
const tables = ref([])
const total = ref(0)
const loading = ref(false)
const range = ref(null)
const filters = reactive({ table_id: null, user: '', action: '', page: 1, page_size: 50 })
const diffVisible = ref(false)
const current = ref(null)

const pretty = (v) => (v ? JSON.stringify(v, null, 2) : '—')

async function load(page) {
  if (page) filters.page = page
  loading.value = true
  try {
    const r = await listAuditLogs({
      table_id: filters.table_id || 0,
      user: filters.user || '',
      action: filters.action || '',
      start: range.value?.[0] || '',
      end: range.value?.[1] ? range.value[1] + ' 23:59:59' : '',
      page: filters.page,
      page_size: filters.page_size,
    })
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function showDiff(row) {
  current.value = row
  diffVisible.value = true
}

onMounted(async () => {
  load(1)
  try {
    tables.value = await listTables({ all: 1 })
  } catch { /* 非管理员时全部表接口被拒，筛选器留空即可 */ }
})
</script>

<style scoped>
.filter-bar { margin-bottom: 8px; }
.pager { margin-top: 12px; justify-content: flex-end; }
.diff-title { font-weight: 600; margin-bottom: 6px; }
.diff-json {
  background: #f5f7fa; padding: 10px; border-radius: 4px; font-size: 12px;
  max-height: 400px; overflow: auto; white-space: pre-wrap; word-break: break-all;
}
</style>
