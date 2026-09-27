<template>
  <div>
    <div class="page-header">
      <h2>通知</h2>
      <div class="header-actions">
        <el-radio-group v-model="tab" size="small" @change="onTabChange">
          <el-radio-button value="inbox">通知</el-radio-button>
          <el-radio-button value="todo">待审批<template v-if="todos.length">（{{ todos.length }}）</template></el-radio-button>
        </el-radio-group>
        <template v-if="tab === 'inbox'">
          <el-radio-group v-model="onlyUnread" size="small" @change="reload">
            <el-radio-button :value="false">全部</el-radio-button>
            <el-radio-button :value="true">只看未读</el-radio-button>
          </el-radio-group>
          <el-button size="small" :disabled="!items.length" @click="readAll">全部已读</el-button>
          <el-button size="small" type="danger" plain @click="clearRead">清空已读</el-button>
        </template>
      </div>
    </div>

    <!-- 通知列表 -->
    <el-card v-if="tab === 'inbox'" v-loading="loading" shadow="never">
      <el-empty v-if="!items.length && !loading" :description="onlyUnread ? '没有未读通知' : '暂无通知'" />
      <div
        v-for="n in items" :key="n.id" class="notify-item" :class="{ unread: !n.read }"
        @click="open(n)"
      >
        <div class="notify-title">
          <span class="title-text">{{ n.title }}</span>
          <span class="notify-time">
            {{ n.created_at }}
            <el-icon class="del-btn" title="删除通知" @click.stop="removeOne(n)"><Delete /></el-icon>
          </span>
        </div>
        <div class="notify-content">{{ n.content }}</div>
        <div v-if="n.link" class="notify-link">点击查看详情 →</div>
      </div>
      <el-pagination
        v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total"
        layout="total, prev, pager, next" style="margin-top: 14px; justify-content: flex-end"
        @current-change="load"
      />
    </el-card>

    <!-- 待审批聚合：我是审批人/归属人的全部等待中审批，不用翻通知找链接 -->
    <el-card v-else v-loading="todoLoading" shadow="never">
      <el-empty v-if="!todos.length && !todoLoading" description="没有待审批的事项" />
      <div v-for="t in todos" :key="t.node_run_id" class="todo-item">
        <div class="todo-head">
          <b>{{ t.title }}</b>
          <span class="todo-wf">来自工作流「{{ t.workflow_name }}」</span>
          <span class="notify-time">{{ t.started_at }}</span>
        </div>
        <div v-if="t.detail" class="notify-content">{{ t.detail }}</div>
        <el-input v-model="comments[t.node_run_id]" type="textarea" :rows="2"
          placeholder="审批意见（可选）" class="todo-comment" />
        <div class="todo-actions">
          <el-button type="success" size="small" :loading="actingId === t.node_run_id"
            @click="act(t, true)">通过</el-button>
          <el-button type="danger" size="small" plain :loading="actingId === t.node_run_id"
            @click="act(t, false)">驳回</el-button>
          <el-link type="primary" size="small" @click="$router.push(`/workflows/runs/${t.run_id}`)">查看运行详情 →</el-link>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { approveWorkflowNode, deleteNotifications, listNotificationsPage, listPendingApprovals, markRead } from '../api'

const router = useRouter()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const onlyUnread = ref(false)

// 待审批 Tab
const tab = ref('inbox')
const todos = ref([])
const todoLoading = ref(false)
const actingId = ref(null)
const comments = reactive({})

async function load() {
  loading.value = true
  try {
    const r = await listNotificationsPage({ page: page.value, page_size: pageSize, only_unread: onlyUnread.value })
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadTodos() {
  todoLoading.value = true
  try {
    todos.value = await listPendingApprovals()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    todoLoading.value = false
  }
}

function onTabChange() {
  if (tab.value === 'todo') loadTodos()
}

function reload() {
  page.value = 1
  load()
}

async function open(n) {
  if (!n.read) {
    await markRead({ ids: [n.id] }).catch(() => {})
    n.read = true
    window.dispatchEvent(new Event('grt-notify-refresh'))   // 同步侧边菜单的未读角标
  }
  if (n.link) router.push(n.link)
}

async function readAll() {
  await markRead({ all: true }).catch(() => {})
  items.value.forEach((n) => { n.read = true })
  window.dispatchEvent(new Event('grt-notify-refresh'))
  if (onlyUnread.value) reload()
}

// 删除单条（悬停显示删除按钮，不冒泡到打开通知）；删了未读要同步侧边未读角标
async function removeOne(n) {
  try {
    await deleteNotifications({ ids: [n.id] })
    items.value = items.value.filter((x) => x.id !== n.id)
    total.value -= 1
    if (!n.read) window.dispatchEvent(new Event('grt-notify-refresh'))
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// 清空全部已读通知（未读保留），需确认
async function clearRead() {
  try {
    await ElMessageBox.confirm('删除全部已读通知？（未读通知会保留）', '清空已读',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' })
  } catch { return }
  try {
    const r = await deleteNotifications({ read_only: true })
    ElMessage.success(`已清空 ${r.deleted} 条已读通知`)
    reload()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function act(t, approved) {
  actingId.value = t.node_run_id
  try {
    await approveWorkflowNode(t.node_run_id, approved, comments[t.node_run_id] || '')
    ElMessage.success(approved ? '已通过，流程继续执行' : '已驳回')
    await loadTodos()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actingId.value = null
  }
}

onMounted(() => { load(); loadTodos() })
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.notify-item {
  padding: 12px 14px; border-radius: 8px; cursor: pointer; margin-bottom: 6px;
  border: 1px solid transparent;
}
.notify-item:hover { background: #f5f7fa; border-color: #e4e7ed; }
.notify-item.unread { background: #ecf5ff; }
.notify-title { font-size: 14px; display: flex; justify-content: space-between; gap: 12px; }
.notify-item.unread .title-text { font-weight: 600; }
.notify-item.unread .title-text::before {
  content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #f56c6c; margin-right: 7px; vertical-align: 1px;
}
.notify-time { color: #c0c4cc; font-size: 12px; flex-shrink: 0; }
.del-btn { margin-left: 6px; vertical-align: -2px; cursor: pointer; opacity: 0; transition: opacity .15s; }
.notify-item:hover .del-btn { opacity: 1; }
.del-btn:hover { color: #f56c6c; }
.notify-content { font-size: 13px; color: #606266; margin-top: 4px; white-space: pre-wrap; }
.notify-link { font-size: 12px; color: #409eff; margin-top: 4px; }
.todo-item { padding: 12px 14px; border: 1px solid #e4e7ed; border-radius: 8px; margin-bottom: 10px; }
.todo-head { display: flex; align-items: center; gap: 10px; }
.todo-wf { font-size: 12px; color: #909399; flex: 1; }
.todo-comment { margin-top: 8px; }
.todo-actions { margin-top: 8px; display: flex; align-items: center; gap: 10px; }
</style>
