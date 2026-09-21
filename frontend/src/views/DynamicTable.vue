<template>
  <div v-loading="metaLoading">
    <div class="page-header">
      <h2>{{ meta?.label || '数据表' }}</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增记录</el-button>
    </div>

    <!-- 动态筛选区 -->
    <el-card v-if="filterable.length" style="margin-bottom: 14px">
      <el-form inline>
        <el-form-item v-for="f in filterable" :key="f.field_name" :label="f.label">
          <el-select
            v-if="f.widget === 'select'" v-model="filterModel[f.field_name]" clearable
            style="width: 160px" placeholder="全部"
          >
            <el-option
              v-for="opt in fieldOptions(f)" :key="String(opt.value)" :label="opt.label" :value="opt.value"
            />
          </el-select>
          <el-select v-else-if="f.widget === 'switch'" v-model="filterModel[f.field_name]" clearable style="width: 120px" placeholder="全部">
            <el-option label="是" :value="true" /><el-option label="否" :value="false" />
          </el-select>
          <el-input-number
            v-else-if="f.widget === 'number'" v-model="filterModel[f.field_name]"
            controls-position="right" style="width: 150px" placeholder="等于"
          />
          <el-date-picker
            v-else-if="f.widget === 'date-picker' || f.widget === 'datetime-picker'"
            v-model="filterModel[f.field_name]" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始" end-placeholder="结束" style="width: 240px"
          />
          <el-input v-else v-model="filterModel[f.field_name]" clearable placeholder="包含..." style="width: 180px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 动态列表 -->
    <el-table :data="rows" v-loading="loading" border stripe @sort-change="onSortChange">
      <el-table-column type="index" width="50" label="#" />
      <el-table-column
        v-for="f in listFields" :key="f.field_name"
        :prop="f.field_name" :label="f.label" sortable="custom"
        :formatter="(row) => fmt(f, row[f.field_name])" show-overflow-tooltip min-width="110"
      />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确定删除该记录？" @confirm="del(row)">
            <template #reference>
              <el-button text type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>暂无数据</template>
    </el-table>

    <el-pagination
      v-model:current-page="page" v-model:page-size="pageSize"
      :total="total" layout="total, sizes, prev, pager, next"
      style="margin-top: 14px" @current-change="load" @size-change="load"
    />

    <el-dialog
      v-model="dialogVisible" :title="editing ? '编辑记录' : '新增记录'"
      width="640px" destroy-on-close
    >
      <DynamicForm
        :fields="meta.fields" :initial="editing || {}" :loading="saving"
        :table-id="tableId" :record-id="editing?.id || null"
        @submit="onSave" @cancel="dialogVisible = false"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import DynamicForm from '../components/DynamicForm.vue'
import { createRecord, deleteRecord, getTable, listRecords, updateRecord } from '../api'

const route = useRoute()
const tableId = Number(route.params.id)

const meta = ref(null)
const metaLoading = ref(true)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const sortBy = ref(null)
const sortOrder = ref(null)
const filterModel = reactive({})
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)

const fields = computed(() => meta.value?.fields || [])
const listFields = computed(() => fields.value.filter((f) => f.options?.show_in_list !== false))
const filterable = computed(() =>
  fields.value.filter((f) =>
    ['input', 'select', 'switch', 'number', 'date-picker', 'datetime-picker'].includes(f.widget)
  )
)

function fmt(f, val) {
  if (val === null || val === undefined) return ''
  if (f.data_type === 'bool') return val ? '是' : '否'
  if (f.data_type === 'date') return String(val).slice(0, 10)
  if (f.data_type === 'datetime') return String(val).replace('T', ' ').slice(0, 19)
  return val
}

function fieldOptions(f) {
  return (f.options?.options || []).map((o) =>
    typeof o === 'object' && o !== null ? o : { label: String(o), value: o }
  )
}

function buildFilters() {
  const filters = []
  for (const f of filterable.value) {
    const v = filterModel[f.field_name]
    if (v === null || v === undefined || v === '') continue
    if (f.widget === 'date-picker' || f.widget === 'datetime-picker') {
      if (Array.isArray(v) && v.length === 2) {
        filters.push({ field: f.field_name, op: 'gte', value: v[0] })
        filters.push({ field: f.field_name, op: 'lte', value: f.widget === 'datetime-picker' ? `${v[1]} 23:59:59` : v[1] })
      }
    } else if (f.widget === 'input') {
      filters.push({ field: f.field_name, op: 'contains', value: v })
    } else {
      filters.push({ field: f.field_name, op: 'eq', value: v })
    }
  }
  return filters
}

async function load() {
  loading.value = true
  try {
    const res = await listRecords(tableId, {
      page: page.value,
      page_size: pageSize.value,
      sort_by: sortBy.value || undefined,
      sort_order: sortOrder.value || undefined,
      filters: JSON.stringify(buildFilters()),
    })
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  for (const k of Object.keys(filterModel)) filterModel[k] = null
  search()
}

function onSortChange({ prop, order }) {
  sortBy.value = order ? prop : null
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  load()
}

function openCreate() {
  editing.value = null
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  dialogVisible.value = true
}

async function onSave(values) {
  saving.value = true
  try {
    if (editing.value) {
      await updateRecord(tableId, editing.value.id, values)
    } else {
      await createRecord(tableId, values)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function del(row) {
  try {
    await deleteRecord(tableId, row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  try {
    meta.value = await getTable(tableId)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    metaLoading.value = false
  }
  load()
})
</script>
