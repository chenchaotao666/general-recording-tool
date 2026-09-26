<template>
  <div v-loading="metaLoading">
    <div class="page-header">
      <h2>
        {{ meta?.label || '数据表' }}
        <el-tag v-if="meta && !meta.is_owner" size="small" style="margin-left: 8px">来自 {{ meta.owner_label }} 的分享</el-tag>
      </h2>
      <div>
        <el-button v-if="canAlter" :icon="SetUp" @click="openStruct">表结构</el-button>
        <el-button :icon="Download" @click="exportXlsx">导出 Excel</el-button>
        <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate">新增记录</el-button>
      </div>
    </div>

    <!-- 动态筛选区：快捷（各字段 AND）/ 高级（规则编辑器，支持 全部/任一 条件） -->
    <el-card v-if="filterable.length || fields.length" style="margin-bottom: 14px">
      <el-radio-group v-model="filterMode" size="small" style="margin-bottom: 10px">
        <el-radio-button value="quick">快捷筛选</el-radio-button>
        <el-radio-button value="advanced">高级筛选</el-radio-button>
      </el-radio-group>
      <el-form v-if="filterMode === 'quick'" inline>
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
      <template v-else>
        <!-- 与工作流筛选条件同一组件；reactive 对象不能整体替换，手动拆赋值 -->
        <FiltersEditor :model-value="advFilters" :fields="fields"
          @update:model-value="(v) => { advFilters.logic = v.logic; advFilters.rules = v.rules }" />
        <div style="margin-top: 8px">
          <el-button type="primary" size="small" @click="search">查询</el-button>
          <el-button size="small" @click="resetFilters">重置</el-button>
        </div>
      </template>
    </el-card>

    <!-- 动态列表 -->
    <el-table :data="rows" v-loading="loading" border stripe @sort-change="onSortChange">
      <el-table-column type="index" width="50" label="#" />
      <el-table-column
        v-for="f in listFields" :key="f.field_name"
        :prop="f.field_name" :label="f.label" sortable="custom"
        show-overflow-tooltip min-width="110"
      >
        <template #default="{ row }">
          <template v-if="f.data_type === 'image'">
            <el-image
              v-for="id in asImageList(row[f.field_name]).slice(0, 3)" :key="id"
              :src="imageUrl(id)" :preview-src-list="asImageList(row[f.field_name]).map(imageUrl)"
              :initial-index="asImageList(row[f.field_name]).indexOf(id)"
              fit="cover" preview-teleported hide-on-click-modal class="cell-thumb"
            />
            <span v-if="asImageList(row[f.field_name]).length > 3" class="thumb-more">
              +{{ asImageList(row[f.field_name]).length - 3 }}
            </span>
          </template>
          <span v-else>{{ fmt(f, row[f.field_name]) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="canEdit || canDelete" label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canEdit" text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm v-if="canDelete" title="确定删除该记录？" @confirm="del(row)">
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

    <!-- 表结构编辑：加/删/改/重命名字段（仅主人/admin 可见） -->
    <el-drawer v-model="structVisible" title="表结构设置" size="600px">
      <el-form label-width="70px" style="max-width: 400px">
        <el-form-item label="表名称">
          <el-input v-model="structLabel" maxlength="64" />
        </el-form-item>
      </el-form>
      <el-divider content-position="left">字段（{{ structRows.length }}）</el-divider>
      <div class="struct-head struct-row">
        <span class="sr-label">显示名</span>
        <span class="sr-name">字段名（英文）</span>
        <span class="sr-type">类型</span>
        <span class="sr-null">可空</span>
        <span class="sr-del" />
      </div>
      <div v-for="(r, i) in structRows" :key="r._key" class="struct-row">
        <el-input v-model="r.label" placeholder="如：金额" class="sr-label" />
        <el-input v-model="r.field_name" placeholder="如：amount" class="sr-name" />
        <el-select v-model="r.data_type" class="sr-type" :disabled="!!r.id && meta?.storage_mode !== 'json'">
          <el-option v-for="t in DATA_TYPES" :key="t" :label="t" :value="t" />
        </el-select>
        <el-checkbox v-model="r.nullable" class="sr-null" />
        <el-button text type="danger" size="small" class="sr-del" @click="structRows.splice(i, 1)">删</el-button>
      </div>
      <el-button text type="primary" size="small" @click="addStructRow">+ 添加字段</el-button>
      <div v-if="meta?.storage_mode !== 'json'" class="struct-hint">
        physical 模式表暂不支持修改已有字段类型（可加/删/改名字段）
      </div>
      <div class="struct-hint">
        修改类型会尝试转换存量数据（转不了的值将被清空）；删除字段会连带删除存量数据中的该字段。
      </div>
      <div class="struct-footer">
        <el-button @click="structVisible = false">取消</el-button>
        <el-button type="primary" :loading="structSaving" @click="saveStruct">保存修改</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Download, SetUp } from '@element-plus/icons-vue'
import DynamicForm from '../components/DynamicForm.vue'
import FiltersEditor from '../components/workflow/FiltersEditor.vue'
import { alterTable, createRecord, deleteRecord, getTable, imageUrl, listRecords, recordExportUrl, updateRecord, updateTable } from '../api'

const DATA_TYPES = ['varchar', 'text', 'int', 'decimal', 'date', 'datetime', 'bool', 'image']
const WIDGET_OF = {
  varchar: 'input', text: 'textarea', int: 'number', decimal: 'number',
  date: 'date-picker', datetime: 'datetime-picker', bool: 'switch', image: 'image-uploader',
}

// 图片列兜底：值可能是 list / JSON 字符串 / null
function asImageList(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.startsWith('[')) {
    try { return JSON.parse(v) } catch { return [] }
  }
  return []
}

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
// 高级筛选：规则编辑器（与工作流筛选条件同一组件），{logic: AND|OR, rules}
const filterMode = ref('quick')
const advFilters = reactive({ logic: 'AND', rules: [] })
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)

const fields = computed(() => meta.value?.fields || [])
const canCreate = computed(() => meta.value?.my_perms?.can_create)
const canEdit = computed(() => meta.value?.my_perms?.can_edit)
const canAlter = computed(() => meta.value?.is_owner || meta.value?.my_perms?.is_admin)
const canDelete = computed(() => meta.value?.my_perms?.can_delete)
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
  // 高级筛选：{logic, rules} 对象形态（支持 任一条件/OR）；快捷筛选：平铺数组（AND）
  if (filterMode.value === 'advanced') {
    const rules = (advFilters.rules || []).filter((r) => r.field && r.op)
    return rules.length ? { logic: advFilters.logic || 'AND', rules } : []
  }
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

// 导出按当前筛选/排序条件（与列表同口径），上限 5000 条
function exportXlsx() {
  const f = buildFilters()
  const has = Array.isArray(f) ? f.length > 0 : (f.rules || []).length > 0
  window.open(recordExportUrl(tableId, {
    sort_by: sortBy.value || undefined,
    sort_order: sortOrder.value || undefined,
    filters: has ? JSON.stringify(f) : undefined,
  }), '_blank')
}

function queryParams() {
  return {
    page: page.value,
    page_size: pageSize.value,
    sort_by: sortBy.value || undefined,
    sort_order: sortOrder.value || undefined,
    filters: JSON.stringify(buildFilters()),
  }
}

async function load() {
  loading.value = true
  try {
    const res = await listRecords(tableId, queryParams())
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// 静默刷新：轮询用，不闪 loading、失败不打扰
async function silentLoad() {
  try {
    const res = await listRecords(tableId, queryParams())
    rows.value = res.items
    total.value = res.total
  } catch { /* 静默刷新失败不打断用户 */ }
}

// 后台写入（工作流定时/webhook、其他同事编辑）感知：页面可见时每 15s 静默刷新
let pollTimer = null
function startPoll() {
  stopPoll()
  pollTimer = setInterval(() => {
    if (document.hidden || loading.value || dialogVisible.value) return
    silentLoad()
  }, 15000)
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// 同页写入（AI 助手填表等）即时刷新：监听应用内广播
function onRecordsChanged(e) {
  if (Number(e.detail?.table_id) === tableId) load()
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  for (const k of Object.keys(filterModel)) filterModel[k] = null
  advFilters.logic = 'AND'
  advFilters.rules = []
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

// ---------- 表结构编辑 ----------
const structVisible = ref(false)
const structSaving = ref(false)
const structLabel = ref('')
const structRows = ref([])
const origFields = ref([])
let structKeySeq = 0

function openStruct() {
  structLabel.value = meta.value?.label || ''
  origFields.value = JSON.parse(JSON.stringify(meta.value?.fields || []))
  structRows.value = origFields.value.map((f) => ({ ...f, _key: ++structKeySeq }))
  structVisible.value = true
}

function addStructRow() {
  structRows.value.push({
    id: null, _key: ++structKeySeq, label: '', field_name: '',
    data_type: 'varchar', nullable: true, widget: 'input', options: {},
  })
}

function buildStructOps() {
  const ops = []
  const origById = new Map(origFields.value.map((f) => [f.id, f]))
  const seenIds = new Set()
  for (const r of structRows.value) {
    if (r.id) {
      seenIds.add(r.id)
      const orig = origById.get(r.id)
      if (!orig) continue
      if (r.field_name !== orig.field_name) {
        ops.push({
          op: 'rename_field', field_name: orig.field_name, new_field_name: r.field_name,
          ...(r.label !== orig.label ? { label: r.label } : {}),
        })
        const upd = { op: 'update_field', field_name: r.field_name }
        if (r.data_type !== orig.data_type) upd.data_type = r.data_type
        if (r.nullable !== orig.nullable) upd.nullable = r.nullable
        if (Object.keys(upd).length > 2) ops.push(upd)
      } else {
        const upd = { op: 'update_field', field_name: r.field_name }
        if (r.label !== orig.label) upd.label = r.label
        if (r.data_type !== orig.data_type) upd.data_type = r.data_type
        if (r.nullable !== orig.nullable) upd.nullable = r.nullable
        if (Object.keys(upd).length > 2) ops.push(upd)
      }
    } else if (r.field_name.trim()) {
      ops.push({
        op: 'add_field',
        field: {
          field_name: r.field_name.trim(), label: r.label.trim() || r.field_name.trim(),
          data_type: r.data_type, nullable: r.nullable, widget: WIDGET_OF[r.data_type] || 'input',
        },
      })
    }
  }
  for (const f of origFields.value) {
    if (!seenIds.has(f.id)) ops.push({ op: 'delete_field', field_name: f.field_name })
  }
  return ops
}

async function saveStruct() {
  const ops = buildStructOps()
  const labelChanged = structLabel.value.trim() && structLabel.value.trim() !== meta.value?.label
  if (!ops.length && !labelChanged) { structVisible.value = false; return }
  const destructive = ops.filter((o) => o.op === 'delete_field' || (o.op === 'update_field' && o.data_type))
  if (destructive.length) {
    await ElMessageBox.confirm(
      '本次修改包含删除字段或修改字段类型，存量数据可能受影响（删除的字段数据将被清除、无法转换的值将被置空）。确定继续？',
      '修改确认', { type: 'warning', confirmButtonText: '继续保存', cancelButtonText: '再想想' },
    )
  }
  structSaving.value = true
  try {
    if (labelChanged) await updateTable(tableId, { label: structLabel.value.trim() })
    let result = null
    if (ops.length) result = await alterTable(tableId, ops)
    ElMessage.success(result?.changes?.length ? `已更新：${result.changes.join('；')}` : '已保存')
    if (result?.warnings?.length) ElMessage.warning(result.warnings.join('；'))
    structVisible.value = false
    meta.value = await getTable(tableId)
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || e)
  } finally {
    structSaving.value = false
  }
}

async function reloadMeta() {
  try { meta.value = await getTable(tableId) } catch { /* 静默 */ }
}

// AI 助手改了表结构时，元数据即时重载（字段列随之更新）
function onTableMetaChanged(e) {
  if (Number(e.detail?.table_id) === tableId) reloadMeta()
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
  window.addEventListener('grt:records-changed', onRecordsChanged)
  window.addEventListener('grt:table-meta-changed', onTableMetaChanged)
  startPoll()
})

onUnmounted(() => {
  window.removeEventListener('grt:records-changed', onRecordsChanged)
  window.removeEventListener('grt:table-meta-changed', onTableMetaChanged)
  stopPoll()
})
</script>

<style scoped>
.struct-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.struct-head { font-size: 12px; color: #909399; }
.sr-label { width: 130px; }
.sr-name { width: 150px; }
.sr-type { width: 110px; }
.sr-null { width: 40px; }
.sr-del { width: 36px; }
.struct-hint { font-size: 12px; color: #909399; margin-top: 10px; }
.struct-footer { margin-top: 18px; display: flex; justify-content: flex-end; gap: 8px; }
.cell-thumb { width: 40px; height: 40px; border-radius: 4px; margin-right: 4px; vertical-align: middle; }
.thumb-more { font-size: 12px; color: #909399; }
</style>
