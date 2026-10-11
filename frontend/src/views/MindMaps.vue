<template>
  <div>
    <div class="page-header">
      <h2>思维导图</h2>
      <el-button type="primary" :icon="Plus" @click="create">新建导图</el-button>
    </div>

    <!-- 列表工具栏：搜索 + 创建人筛选（与工作流列表同款） -->
    <div class="list-filter">
      <el-input v-model="kw" placeholder="搜索导图标题" clearable size="small" style="width: 220px" />
      <el-select v-model="ownerFilter" placeholder="全部创建人" clearable size="small" style="width: 140px">
        <el-option v-for="o in ownerOptions" :key="o" :label="o" :value="o" />
      </el-select>
    </div>

    <el-table :data="filtered" v-loading="loading" border>
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" @click="$router.push(`/mindmaps/${row.id}`)">{{ row.title }}</el-link>
          <el-tag v-if="row.shared" size="small" :type="row.can_edit ? 'success' : 'info'" effect="plain" style="margin-left: 6px">
            {{ row.can_edit ? '分享·可编辑' : '分享·只读' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="owner_name" label="创建人" width="130" show-overflow-tooltip />
      <el-table-column label="更新时间" width="150" :formatter="(r) => fmtTime(r.updated_at)" />
      <el-table-column label="创建时间" width="150" :formatter="(r) => fmtTime(r.created_at)" />
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="$router.push(`/mindmaps/${row.id}`)">打开</el-button>
          <el-button text size="small" @click="rename(row)">重命名</el-button>
          <el-button text type="primary" size="small" @click="openShare(row)">分享</el-button>
          <el-popconfirm v-if="row.can_delete" title="确定删除该导图？" width="220" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="kw || ownerFilter ? '没有匹配的导图' : '还没有思维导图，点右上角新建'" />
      </template>
    </el-table>

    <!-- 分享（与数据表共用同一个对话框组件） -->
    <ShareDialog
      v-model="shareVisible" resource-type="mindmap"
      :resource-id="shareTarget?.id" :resource-name="shareTarget?.title"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { createMindmap, deleteMindmap, listMindmaps, updateMindmap } from '../api'
import ShareDialog from '../components/ShareDialog.vue'
import { fmtTime } from '../utils/format'

const router = useRouter()
const rows = ref([])
const loading = ref(false)
const kw = ref('')
const ownerFilter = ref('')

// 分享
const shareVisible = ref(false)
const shareTarget = ref(null)

const ownerOptions = computed(() => [...new Set(rows.value.map((r) => r.owner_name))])

// 关键字（标题，不区分大小写）× 创建人 过滤
const filtered = computed(() => rows.value.filter((r) => {
  if (kw.value && !r.title.toLowerCase().includes(kw.value.trim().toLowerCase())) return false
  if (ownerFilter.value && r.owner_name !== ownerFilter.value) return false
  return true
}))

async function load() {
  loading.value = true
  try {
    rows.value = await listMindmaps()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openShare(row) {
  shareTarget.value = row
  shareVisible.value = true
}

// 重命名：列表页直接改（不用进编辑器）
async function rename(row) {
  let title
  try {
    const r = await ElMessageBox.prompt('导图标题', '重命名', {
      confirmButtonText: '保存', cancelButtonText: '取消',
      inputValue: row.title, inputPattern: /\S+/, inputErrorMessage: '标题不能为空',
    })
    title = r.value
  } catch { return }
  try {
    await updateMindmap(row.id, { title: title.trim() })
    row.title = title.trim()
    ElMessage.success('已重命名')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function create() {
  let title
  try {
    const r = await ElMessageBox.prompt('导图标题', '新建思维导图', {
      confirmButtonText: '创建', cancelButtonText: '取消',
      inputPlaceholder: '未命名导图',
    })
    title = r.value
  } catch { return }
  try {
    const m = await createMindmap({ title: (title || '').trim() || undefined })
    router.push(`/mindmaps/${m.id}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function del(row) {
  try {
    await deleteMindmap(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
/* .page-header 用 App.vue 全局样式，不在此重复定义 */
.list-filter { display: flex; gap: 10px; margin-bottom: 12px; }
/* 列内容不换行：标题超长省略号（tooltip 展示全名） */
:deep(.el-table .cell) { white-space: nowrap; }
</style>
