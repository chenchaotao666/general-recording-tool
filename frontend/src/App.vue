<template>
  <router-view v-if="$route.path === '/login' || $route.path.startsWith('/share/')" />
  <el-container v-else class="layout">
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
        <template v-if="user?.role === 'admin'">
          <el-menu-item index="/system/users">
            <el-icon><User /></el-icon><span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/system/roles">
            <el-icon><Avatar /></el-icon><span>角色管理</span>
          </el-menu-item>
          <el-menu-item index="/system/permissions">
            <el-icon><Key /></el-icon><span>权限管理</span>
          </el-menu-item>
          <el-menu-item index="/system/groups">
            <el-icon><UserFilled /></el-icon><span>用户组</span>
          </el-menu-item>
        </template>
        <el-menu-item index="/friends">
          <el-icon><User /></el-icon><span>好友</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <span />
        <div class="topbar-right">
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
          <el-dropdown>
            <span class="user-name">{{ user?.username || '用户' }}（{{ roleLabel }}）</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="pwdVisible = true">修改密码</el-dropdown-item>
                <el-dropdown-item @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 修改密码 -->
      <el-dialog v-model="pwdVisible" title="修改密码" width="400px" destroy-on-close>
        <el-form label-width="80px">
          <el-form-item label="原密码">
            <el-input v-model="pwdForm.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
          </el-form-item>
          <el-form-item label="确认密码">
            <el-input v-model="pwdForm.confirm" type="password" show-password />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="pwdVisible = false">取消</el-button>
          <el-button type="primary" :loading="pwdSaving" @click="changePassword">确定</el-button>
        </template>
      </el-dialog>
      <el-main class="main">
        <router-view />
      </el-main>
      <AssistantPanel />
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { AlarmClock, Avatar, Bell, DataAnalysis, Grid, Key, Setting, Upload, User, UserFilled } from '@element-plus/icons-vue'
import { changePassword as changePasswordApi, listNotifications, markRead, unreadCount } from './api'
import AssistantPanel from './components/AssistantPanel.vue'

const router = useRouter()
const route = useRoute()
const unread = ref(0)
const notifications = ref([])

// 根组件只创建一次：登录/切换账号后 localStorage 已更新但组件不会重建，
// 需在路由变化时重新读取当前用户
function readUser() {
  return JSON.parse(localStorage.getItem('grt_user') || 'null')
}
const user = ref(readUser())
watch(() => route.path, () => {
  user.value = readUser()
  // 登录/切换账号后路由首次变化时立即拉取通知（否则要等下一个 30s 轮询周期）
  if (localStorage.getItem('grt_token')) {
    pollUnread()
    loadNotifications()
  }
})
const roleLabel = computed(() => ({ admin: '管理员', vip: 'VIP', user: '普通用户' }[user.value?.role] || '普通用户'))
let timer = null

function logout() {
  localStorage.removeItem('grt_token')
  localStorage.removeItem('grt_user')
  router.push('/login')
}

// 修改密码
const pwdVisible = ref(false)
const pwdSaving = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })

async function changePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) return ElMessage.warning('请填写完整')
  if (pwdForm.new_password.length < 6) return ElMessage.warning('新密码至少 6 位')
  if (pwdForm.new_password !== pwdForm.confirm) return ElMessage.warning('两次输入的新密码不一致')
  pwdSaving.value = true
  try {
    await changePasswordApi(pwdForm.old_password, pwdForm.new_password)
    ElMessage.success('密码已修改')
    pwdVisible.value = false
    Object.assign(pwdForm, { old_password: '', new_password: '', confirm: '' })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    pwdSaving.value = false
  }
}

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
  // 未登录（停留在 /login）时不发请求，避免 401 触发拦截器的清理逻辑
  if (localStorage.getItem('grt_token')) pollUnread()
  timer = setInterval(() => {
    if (localStorage.getItem('grt_token')) pollUnread()
  }, 30000)
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
.topbar-right { display: flex; align-items: center; gap: 16px; }
/* 角标默认向上探出 wrapper 一半高度，在 48px 顶栏里会被上沿裁掉，改为完全落在按钮内侧 */
.bell .el-badge__content { top: 8px; right: 12px; transform: translateX(100%); }
.user-name { cursor: pointer; font-size: 14px; color: #606266; outline: none; }
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
