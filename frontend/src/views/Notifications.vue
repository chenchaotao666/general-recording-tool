<template>
  <div>
    <div class="page-header">
      <h2>通知</h2>
      <div class="header-actions">
        <el-radio-group v-model="onlyUnread" size="small" @change="reload">
          <el-radio-button :value="false">全部</el-radio-button>
          <el-radio-button :value="true">只看未读</el-radio-button>
        </el-radio-group>
        <el-button size="small" :disabled="!items.length" @click="readAll">全部已读</el-button>
      </div>
    </div>

    <el-card v-loading="loading" shadow="never">
      <el-empty v-if="!items.length && !loading" :description="onlyUnread ? '没有未读通知' : '暂无通知'" />
      <div
        v-for="n in items" :key="n.id" class="notify-item" :class="{ unread: !n.read }"
        @click="open(n)"
      >
        <div class="notify-title">
          <span class="title-text">{{ n.title }}</span>
          <span class="notify-time">{{ n.created_at }}</span>
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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listNotificationsPage, markRead } from '../api'

const router = useRouter()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const onlyUnread = ref(false)

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

onMounted(load)
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
.notify-content { font-size: 13px; color: #606266; margin-top: 4px; white-space: pre-wrap; }
.notify-link { font-size: 12px; color: #409eff; margin-top: 4px; }
</style>
