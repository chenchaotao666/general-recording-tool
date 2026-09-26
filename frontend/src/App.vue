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
        <el-menu-item index="/notes">
          <el-icon><Notebook /></el-icon><span>记事本</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DataAnalysis /></el-icon><span>报表</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><AlarmClock /></el-icon><span>任务规则</span>
        </el-menu-item>
        <el-menu-item index="/workflows">
          <el-icon><Connection /></el-icon><span>工作流</span>
        </el-menu-item>
        <el-menu-item index="/notifications">
          <el-icon><Bell /></el-icon><span>通知</span>
          <span v-if="unread" class="menu-unread">{{ unread > 99 ? '99+' : unread }}</span>
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
        </template>
        <el-menu-item index="/friends">
          <el-icon><User /></el-icon><span>好友</span>
        </el-menu-item>
        <el-menu-item index="/system/groups">
          <el-icon><UserFilled /></el-icon><span>用户组</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon><span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <span />
        <div class="topbar-right">
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
import { AlarmClock, Avatar, Bell, Connection, DataAnalysis, Grid, Key, Notebook, Setting, Upload, User, UserFilled } from '@element-plus/icons-vue'
import { changePassword as changePasswordApi, unreadCount } from './api'
import AssistantPanel from './components/AssistantPanel.vue'

const router = useRouter()
const route = useRoute()
const unread = ref(0)

// 根组件只创建一次：登录/切换账号后 localStorage 已更新但组件不会重建，
// 需在路由变化时重新读取当前用户
function readUser() {
  return JSON.parse(localStorage.getItem('grt_user') || 'null')
}
const user = ref(readUser())
watch(() => route.path, () => {
  user.value = readUser()
  // 登录/切换账号后路由首次变化时立即拉取未读数（否则要等下一个 30s 轮询周期）
  if (localStorage.getItem('grt_token')) pollUnread()
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

onMounted(() => {
  // 未登录（停留在 /login）时不发请求，避免 401 触发拦截器的清理逻辑
  if (localStorage.getItem('grt_token')) pollUnread()
  // 通知页标记已读后广播此事件，角标立即刷新
  window.addEventListener('grt-notify-refresh', pollUnread)
  timer = setInterval(() => {
    if (localStorage.getItem('grt_token')) pollUnread()
  }, 30000)
})
onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('grt-notify-refresh', pollUnread)
})
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
/* 侧边菜单的未读数角标 */
.menu-unread {
  margin-left: auto; background: #f56c6c; color: #fff; font-size: 11px; line-height: 1;
  border-radius: 9px; padding: 3px 6px; transform: scale(.9);
}
.user-name { cursor: pointer; font-size: 14px; color: #606266; outline: none; }
.main { background: #f5f7fa; padding: 20px 24px; overflow-y: auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
</style>
