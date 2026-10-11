<template>
  <div>
    <div class="page-header">
      <h2>数据表</h2>
      <div class="page-header-ops">
        <!-- 搜索/排序（客户端，表多时不用肉眼扫卡片） -->
        <el-input
          v-if="tables.length > 3" v-model="kw" placeholder="搜索表名" clearable
          :prefix-icon="SearchIcon" style="width: 180px"
        />
        <el-select v-if="tables.length > 3" v-model="sortMode" style="width: 130px">
          <el-option label="最近创建" value="created_desc" />
          <el-option label="最早创建" value="created_asc" />
          <el-option label="名称 A→Z" value="label_asc" />
        </el-select>
        <el-badge :value="pendingShares.length || ''" :hidden="!pendingShares.length">
          <el-button @click="pendingVisible = true">待接受分享</el-button>
        </el-badge>
        <el-button :icon="Plus" @click="createVisible = true">新建空白表</el-button>
        <el-button type="primary" :icon="Upload" @click="$router.push('/import')">导入 Excel 建表</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && tables.length === 0" description="还没有数据表">
      <el-button :icon="Plus" @click="createVisible = true">新建空白表</el-button>
      <el-button type="primary" :icon="Upload" @click="$router.push('/import')">导入 Excel 建表</el-button>
    </el-empty>
    <el-empty v-else-if="!loading && !displayTables.length" :description="`没有匹配「${kw}」的数据表`" />

    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="t in displayTables" :key="t.id" :xs="24" :sm="12" :md="8" :xl="6" style="margin-bottom: 16px">
        <el-card shadow="hover">
          <div class="card-title">
            {{ t.label }}
            <el-tag v-if="t.storage_mode === 'physical'" size="small" type="warning" style="margin-left: 6px">独立表</el-tag>
            <el-tag v-if="!t.is_owner" size="small" style="margin-left: 6px">来自 {{ t.owner_label }} 的分享</el-tag>
          </div>
          <div class="card-sub">{{ t.name }} · {{ t.record_count }} 条记录</div>
          <div class="card-sub">创建于 {{ fmtTime(t.created_at) }}</div>
          <div style="margin-top: 12px">
            <el-button type="primary" @click="$router.push(`/t/${t.id}`)">打开</el-button>
            <el-button text :icon="Download" @click="exportXlsx(t)">导出</el-button>
            <el-button v-if="canShare(t)" text type="primary" @click="openShare(t)">分享</el-button>
            <el-button v-if="t.is_owner || t.is_admin" type="danger" text @click="del(t)">删除</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新建空白表：不走 Excel 的起步路径（后续可在表页「表结构」里继续加字段） -->
    <el-dialog v-model="createVisible" title="新建空白表" width="420px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="表名称" required>
          <el-input v-model="createForm.label" placeholder="如：客户跟进记录" maxlength="64" @keyup.enter="doCreateTable" />
        </el-form-item>
        <el-form-item label="首个字段">
          <el-input v-model="createForm.firstField" placeholder="默认：名称" maxlength="32" />
          <div class="form-hint">先建一个文本字段起步，更多字段建好后在「表结构」里添加</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreateTable">创建</el-button>
      </template>
    </el-dialog>

    <!-- 待接受的分享 -->
    <el-dialog v-model="pendingVisible" title="待接受的分享" width="620px">
      <el-table :data="pendingShares" size="small" border>
        <el-table-column label="类型" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.resource_type === 'mindmap' ? 'success' : 'info'">
              {{ row.resource_type === 'mindmap' ? '导图' : '数据表' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="名称" prop="table_label" min-width="140" />
        <el-table-column label="分享者" prop="owner_label" width="110" />
        <el-table-column label="权限" min-width="140">
          <template #default="{ row }">{{ permsText(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="respond(row, 'accept')">接受</el-button>
            <el-button text type="danger" size="small" @click="respond(row, 'reject')">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!pendingShares.length" description="暂无待接受的分享" :image-size="60" />
    </el-dialog>

    <!-- 分享管理对话框（与思维导图等共用同一组件） -->
    <ShareDialog
      v-model="shareVisible" resource-type="table"
      :resource-id="shareTable?.id" :resource-name="shareTable?.label"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Download, Search as SearchIcon } from '@element-plus/icons-vue'
import {
  acceptMindmapShare, acceptShare, createTable, deleteTable, listPendingShares, listTables,
  recordExportUrl, rejectMindmapShare, rejectShare,
} from '../api'
import ShareDialog from '../components/ShareDialog.vue'
import { fmtTime } from '../utils/format'
import { useRouter } from 'vue-router'

const router = useRouter()

// 导出整表（上限 5000 条）；打开表页后可按当前筛选导出
function exportXlsx(t) {
  const w = window.open(recordExportUrl(t.id), '_blank')
  if (!w) ElMessage.warning('浏览器拦截了弹出窗口，请允许本站的弹出窗口后重试')
}

const tables = ref([])
const loading = ref(false)

// 搜索/排序（客户端过滤）
const kw = ref('')
const sortMode = ref('created_desc')
const displayTables = computed(() => {
  const k = kw.value.trim().toLowerCase()
  let list = tables.value
  if (k) list = list.filter((t) => (t.label || '').toLowerCase().includes(k) || (t.name || '').toLowerCase().includes(k))
  const arr = [...list]
  if (sortMode.value === 'label_asc') arr.sort((a, b) => (a.label || '').localeCompare(b.label || '', 'zh'))
  else if (sortMode.value === 'created_asc') arr.sort((a, b) => (a.created_at > b.created_at ? 1 : -1))
  else arr.sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
  return arr
})

// ---------- 新建空白表 ----------
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ label: '', firstField: '' })

async function doCreateTable() {
  const label = createForm.label.trim()
  if (!label) return ElMessage.warning('请填写表名称')
  creating.value = true
  try {
    const fieldLabel = createForm.firstField.trim() || '名称'
    const res = await createTable({
      label,
      fields: [{ field_name: 'name', label: fieldLabel, data_type: 'varchar', nullable: false }],
    })
    ElMessage.success(`已创建「${label}」，去添加字段和记录吧`)
    createVisible.value = false
    createForm.label = ''
    createForm.firstField = ''
    window.dispatchEvent(new Event('grt:tables-changed'))
    // 直接进表页，顺势就能加字段/录数据
    if (res?.table?.id) router.push(`/t/${res.table.id}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

const myPerms = JSON.parse(localStorage.getItem('grt_user') || '{}').perms || []

async function load() {
  loading.value = true
  try {
    tables.value = await listTables()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function canShare(t) {
  return (t.is_owner && myPerms.includes('share')) || t.is_admin
}

// L3 不可恢复：删除整表用弹窗确认并说明影响范围
async function del(t) {
  try {
    await ElMessageBox.confirm(
      `将删除数据表「${t.name}」及其全部 ${t.record_count} 条记录，不可恢复。`,
      '删除数据表',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await deleteTable(t.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 分享（对话框逻辑在 ShareDialog 组件） ----------
const shareVisible = ref(false)
const shareTable = ref(null)

function openShare(t) {
  shareTable.value = t
  shareVisible.value = true
}

// ---------- 待接受分享 ----------
const pendingVisible = ref(false)
const pendingShares = ref([])

async function loadPending() {
  try {
    pendingShares.value = await listPendingShares()
  } catch { /* 未登录等场景忽略 */ }
}

function permsText(row) {
  return [
    row.can_view && '查看', row.can_create && '新增',
    row.can_edit && '编辑', row.can_delete && '删除',
  ].filter(Boolean).join(' / ')
}

async function respond(row, action) {
  try {
    const isMm = row.resource_type === 'mindmap'
    await (action === 'accept'
      ? (isMm ? acceptMindmapShare(row.id) : acceptShare(row.id))
      : (isMm ? rejectMindmapShare(row.id) : rejectShare(row.id)))
    ElMessage.success(action === 'accept' ? '已接受' : '已拒绝')
    await Promise.all([loadPending(), load()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => {
  load()
  loadPending()
  // AI 助手建表/填数/改结构后即时刷新列表（含各表记录数）
  window.addEventListener('grt:tables-changed', load)
  window.addEventListener('grt:records-changed', load)
})
onBeforeUnmount(() => {
  window.removeEventListener('grt:tables-changed', load)
  window.removeEventListener('grt:records-changed', load)
})
</script>

<style scoped>
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.card-sub { font-size: 12px; color: #909399; margin-top: 4px; }
.link-url { font-size: 12px; color: #409eff; word-break: break-all; }
.page-header-ops { display: flex; align-items: center; gap: 8px; }
.form-hint { font-size: 12px; color: #909399; margin-top: 4px; line-height: 1.4; }
</style>
