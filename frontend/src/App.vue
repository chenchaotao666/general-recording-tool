<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">通用记录工具</div>
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/tables">
          <el-icon><Grid /></el-icon><span>数据表</span>
        </el-menu-item>
        <el-menu-item index="/import">
          <el-icon><Upload /></el-icon><span>导入 Excel</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><AlarmClock /></el-icon><span>任务规则</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DataAnalysis /></el-icon><span>报表</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon><span>模型设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <span />
        <el-popover placement="bottom-end" width="400" trigger="click" @show="loadNotifications">
          <template #reference>
            <el-badge :value="unread || ''" :hidden="!unread" class="bell">
              <el-button text :icon="Bell" size="large" />
            </el-badge>
          </template>
          <div class="notify-header">
            <span style="font-weight: 600">通知</span>
            <el-button text size="small" :disabled="!unread" @click="readAll">全部已读</el-button>
          </div>
          <div class="notify-list">
            <el-empty v-if="!notifications.length" description="暂无通知" :image-size="60" />
            <div
              v-for="n in notifications" :key="n.id" class="notify-item"
              :class="{ unread: !n.read }" @click="openNotification(n)"
            >
              <div class="notify-title">{{ n.title }}<span class="notify-time">{{ n.created_at }}</span></div>
              <div class="notify-content">{{ n.content }}</div>
            </div>
          </div>
        </el-popover>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { AlarmClock, Bell, DataAnalysis, Grid, Setting, Upload } from '@element-plus/icons-vue'
import { listNotifications, markRead, unreadCount } from './api'

const router = useRouter()
const unread = ref(0)
const notifications = ref([])
let timer = null

async function pollUnread() {
  try {
    unread.value = (await unreadCount()).count
  } catch { /* 后端未启动时静默 */ }
}

async function loadNotifications() {
  try {
    notifications.value = await listNotifications()
  } catch { /* ignore */ }
}

async function openNotification(n) {
  if (!n.read) {
    await markRead({ ids: [n.id] }).catch(() => {})
    n.read = true
    pollUnread()
  }
  if (n.link) router.push(n.link)
}

async function readAll() {
  await markRead({ all: true }).catch(() => {})
  notifications.value.forEach((n) => { n.read = true })
  unread.value = 0
}

onMounted(() => {
  pollUnread()
  timer = setInterval(pollUnread, 30000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style>
body { margin: 0; font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; }
.layout { height: 100vh; }
.aside { border-right: 1px solid #e4e7ed; background: #fafafa; }
.logo { padding: 18px 20px; font-size: 17px; font-weight: 600; color: #303133; }
.aside .el-menu { border-right: none; background: transparent; }
.topbar {
  background: #fff; border-bottom: 1px solid #e4e7ed;
  display: flex; align-items: center; justify-content: space-between; height: 48px;
}
.main { background: #f5f7fa; padding: 20px 24px; overflow-y: auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
.notify-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.notify-list { max-height: 400px; overflow-y: auto; }
.notify-item { padding: 8px 6px; border-radius: 6px; cursor: pointer; }
.notify-item:hover { background: #f5f7fa; }
.notify-item.unread .notify-title { font-weight: 600; }
.notify-item.unread .notify-title::before {
  content: ''; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: #f56c6c; margin-right: 6px; vertical-align: middle;
}
.notify-title { font-size: 13px; }
.notify-time { float: right; color: #c0c4cc; font-size: 12px; font-weight: 400; }
.notify-content { font-size: 12px; color: #606266; margin-top: 2px; }
</style>
