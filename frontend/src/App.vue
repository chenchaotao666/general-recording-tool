<template>
  <!-- 裸页（不带侧边菜单壳）：登录、登录后的选择公司、公开分享/表单/审批 -->
  <router-view v-if="$route.path === '/login' || $route.path === '/select-tenant'
    || $route.path.startsWith('/share/') || $route.path.startsWith('/sf/')" />
  <el-container v-else class="layout" :class="{ focus: focusMode }">
    <el-aside :width="navCollapsed ? '82px' : '180px'" class="aside" :class="{ 'nav-compact': navCollapsed }">
      <router-link to="/home" class="nav-brand" title="万通AI助手" aria-label="万通AI助手首页">
        <img src="/wantong-logo.svg" alt="" class="nav-brand-mark" />
        <span v-if="!navCollapsed" class="nav-brand-name">万通AI助手</span>
      </router-link>
      <el-menu :default-active="activeNavPath" router :collapse-transition="false" aria-label="主导航">
        <el-menu-item index="/home">
          <el-icon><HomeFilled /></el-icon><span>首页</span>
        </el-menu-item>
        <el-menu-item-group>
          <template #title>工作区</template>
          <el-menu-item v-if="hasMenu('menu_tables')" index="/tables">
            <el-icon><Grid /></el-icon><span>数据表</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_smart_tables')" index="/smart">
            <el-icon><Tickets /></el-icon><span>智能表</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_import')" index="/import">
            <el-icon><Upload /></el-icon><span>导入 Excel</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_notes')" index="/notes">
            <el-icon><Notebook /></el-icon><span>记事本</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_whiteboard')" index="/whiteboard">
            <el-icon><Brush /></el-icon><span>画板</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_mindmaps')" index="/mindmaps">
            <el-icon><Share /></el-icon><span>思维导图</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_reports')" index="/reports">
            <el-icon><DataAnalysis /></el-icon><span>报表</span>
          </el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group v-if="hasMenu('menu_notifications') || hasMenu('menu_friends') || hasMenu('menu_groups')">
          <template #title>协作</template>
          <el-menu-item v-if="hasMenu('menu_notifications')" index="/notifications">
            <el-icon><Bell /></el-icon><span>通知</span>
            <span v-if="unread" class="menu-unread">{{ unread > 99 ? '99+' : unread }}</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_friends')" index="/friends">
            <el-icon><Postcard /></el-icon><span>好友</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_groups')" index="/system/groups">
            <el-icon><Collection /></el-icon><span>用户组</span>
          </el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group v-if="user?.is_platform_admin">
          <template #title>平台</template>
          <el-menu-item index="/platform/tenants">
            <el-icon><OfficeBuilding /></el-icon><span>平台租户</span>
          </el-menu-item>
          <el-menu-item index="/platform/plans">
            <el-icon><PriceTag /></el-icon><span>套餐配置</span>
          </el-menu-item>
          <el-menu-item index="/system/users">
            <el-icon><User /></el-icon><span>用户管理</span>
          </el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group>
          <template #title>账户</template>
          <el-menu-item v-if="hasMenu('menu_billing')" index="/billing">
            <el-icon><Wallet /></el-icon><span>套餐与用量</span>
          </el-menu-item>
          <el-menu-item v-if="user?.is_platform_admin" index="/settings">
            <el-icon><Setting /></el-icon><span>集成设置</span>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
      <button type="button" class="collapse-btn" :aria-expanded="!navCollapsed" :aria-label="navCollapsed ? '展开导航' : '收起导航'" :title="navCollapsed ? '展开导航' : '收起导航'" @click="toggleNav">
        <el-icon><Expand v-if="navCollapsed" /><Fold v-else /></el-icon>
      </button>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <span class="page-title">{{ $route.meta.title || '' }}</span>
          <span id="topbarActions" class="topbar-actions" />
        </div>
        <div class="topbar-right">
          <el-icon v-if="$route.meta.flush" class="focus-icon" title="专注模式：隐藏导航与顶栏，编辑区占满窗口（Esc 退出）" @click="focusMode = true"><FullScreen /></el-icon>
          <el-badge :value="unread || ''" :max="99" class="bell-badge">
            <el-icon class="bell-icon" title="通知" @click="router.push('/notifications')"><Bell /></el-icon>
          </el-badge>
          <el-dropdown trigger="click" @command="enterpriseCommand" @visible-change="refreshEnterprises">
            <el-button text class="enterprise-trigger"><el-icon><OfficeBuilding /></el-icon><span>{{ user?.tenant?.type === 'personal' ? '个人空间' : user?.tenant?.name || '我的企业' }}</span><span>⌄</span></el-button>
            <template #dropdown><el-dropdown-menu>
              <el-dropdown-item v-for="t in user?.tenants || []" :key="t.id" :command="t.id" :disabled="t.id === user?.tenant?.id">
                {{ t.id === user?.tenant?.id ? '✓ ' : '' }}{{ t.type === 'personal' ? '个人空间' : t.name }}
              </el-dropdown-item>
              <el-dropdown-item v-if="isEnterprise" divided command="current">我的企业 · 邀请同事</el-dropdown-item>
              <el-dropdown-item divided command="create">＋ 新建企业</el-dropdown-item>
              <el-dropdown-item command="join">加入企业</el-dropdown-item>
            </el-dropdown-menu></template>
          </el-dropdown>
          <el-tag v-if="planTag" :type="planTag.type" size="small">{{ planTag.text }}</el-tag>
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
      <el-alert
        v-if="tenantInfo?.subscription?.status === 'grace' && !bannerHidden('grace')"
        type="warning" closable class="sub-banner" @close="hideBanner('grace')"
        :title="`订阅已到期，宽限期还剩 ${tenantInfo.subscription.grace_remaining_days} 天，宽限期满后将进入只读状态；请联系平台管理员续费`"
      />
      <el-alert
        v-else-if="tenantInfo && !tenantInfo.writable && !bannerHidden('readonly')"
        type="error" closable class="sub-banner" @close="hideBanner('readonly')"
        title="订阅已过期，当前为只读状态；数据完整保留，续费后自动恢复"
      />

      <EnterpriseDialog v-model="enterpriseVisible" :mode="enterpriseMode" @enter="enterEnterprise" @updated="enterpriseUpdated" />
      <!-- 修改密码（即时校验 + 强度提示） -->
      <el-dialog v-model="pwdVisible" title="修改密码" width="400px" destroy-on-close>
        <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px" @submit.prevent>
          <el-form-item label="原密码" prop="old_password">
            <el-input v-model="pwdForm.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
            <div v-if="pwdForm.new_password" class="pwd-strength">
              强度：<span :class="pwdStrength.cls">{{ pwdStrength.text }}</span>
              <span class="pwd-strength-hint">建议 8 位以上，混合字母、数字和符号</span>
            </div>
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm">
            <el-input v-model="pwdForm.confirm" type="password" show-password @keyup.enter="changePassword" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="pwdVisible = false">取消</el-button>
          <el-button type="primary" :loading="pwdSaving" @click="changePassword">确定</el-button>
        </template>
      </el-dialog>
      <el-main class="main" :class="{ 'main-flush': $route.meta.flush }">
        <router-view />
      </el-main>
      <AssistantPanel />
    </el-container>
    <!-- 专注模式下的浮动退出按钮（顶栏已隐藏，需独立出口） -->
    <div v-if="focusMode" class="focus-exit" title="退出专注模式（Esc）" @click="focusMode = false">
      <el-icon><ScaleToOriginal /></el-icon>
    </div>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElLoading, ElMessage } from 'element-plus'
import { Bell, Brush, Collection, DataAnalysis, Expand, Fold, FullScreen, Grid, HomeFilled, Notebook, OfficeBuilding, Postcard, PriceTag, ScaleToOriginal, Setting, Share, Tickets, Upload, User, Wallet } from '@element-plus/icons-vue'
import { changePassword as changePasswordApi, getCurrentTenant, listMyTenants, switchTenant, unreadCount } from './api'
import AssistantPanel from './components/AssistantPanel.vue'
import EnterpriseDialog from './components/EnterpriseDialog.vue'

const router = useRouter()
const route = useRoute()
const unread = ref(0)
// 侧边导航折叠状态（记住选择）
const navCollapsed = ref(localStorage.getItem('grt_nav_collapsed') !== '0')
const activeNavPath = computed(() => {
  const sections = ['/system/groups', '/system/users', '/platform/tenants', '/platform/plans', '/home', '/tables', '/smart', '/import', '/notes', '/whiteboard', '/mindmaps', '/reports', '/notifications', '/friends', '/billing', '/settings']
  return sections.find(path => route.path === path || route.path.startsWith(`${path}/`)) || route.path
})
function toggleNav() {
  navCollapsed.value = !navCollapsed.value
  localStorage.setItem('grt_nav_collapsed', navCollapsed.value ? '1' : '0')
}

// 根组件只创建一次：登录/切换账号后 localStorage 已更新但组件不会重建，
// 需在路由变化时重新读取当前用户
function readUser() {
  return JSON.parse(localStorage.getItem('grt_user') || 'null')
}
const user = ref(readUser())
const tenantInfo = ref(null)   // /tenants/current：套餐/用量/订阅状态（横幅与菜单显隐用）
// 专注模式：隐藏侧边导航与顶栏，编辑区占满窗口（仅 flush 页面可进入；Esc 或右上角悬浮按钮退出）
const focusMode = ref(false)
function onFocusEsc(e) { if (e.key === 'Escape') focusMode.value = false }
watch(focusMode, (on) => {
  if (on) window.addEventListener('keydown', onFocusEsc)
  else window.removeEventListener('keydown', onFocusEsc)
})

// 表格 ID 等页面内参数变化不需要重新拉取全局未读数和租户信息。
watch(() => route.matched[0]?.path || route.path, () => {
  user.value = readUser()
  // 离开编辑器页面时自动退出专注模式（侧边导航被隐藏，避免用户卡在无边框状态）
  if (focusMode.value && !route.meta.flush) focusMode.value = false
  // 登录/切换账号后路由首次变化时立即拉取未读数（否则要等下一个 30s 轮询周期）
  if (localStorage.getItem('grt_token')) {
    pollUnread()
    pollTenant()
  }
})
// 菜单功能权限（角色矩阵可配）：admin 恒全开；老会话 payload 无 perms 字段时放行（重新登录后按配置生效）
const hasMenu = (code) => user.value?.role === 'admin'
  || !Array.isArray(user.value?.perms) || user.value.perms.includes(code)

// 当前空间是否企业版（登录/切换空间 payload 里带 tenant.type，切换后页面会重载）
const isEnterprise = computed(() => ['enterprise', 'private'].includes(user.value?.tenant?.type))
const roleLabel = computed(() => user.value?.role === 'admin' ? '管理员' : '成员')
const planTag = computed(() => {
  const t = tenantInfo.value
  if (!t) return null
  const status = t.subscription?.status
  if (status === 'grace') return { type: 'warning', text: '宽限期' }
  if (!t.writable) return { type: 'danger', text: '已过期·只读' }
  return t.plan ? { type: 'info', text: t.plan.name } : null
})
let timer = null

function logout() {
  localStorage.removeItem('grt_token')
  localStorage.removeItem('grt_user')
  localStorage.removeItem('grt_tenant_id')
  router.push('/login')
}

const enterpriseVisible = ref(false)
const enterpriseMode = ref('create')
function enterpriseCommand(command) {
  if (typeof command === 'number') return switchWorkspace(command)
  enterpriseMode.value = command
  enterpriseVisible.value = true
}
async function refreshEnterprises(open) {
  if (!open || !user.value) return
  try {
    user.value.tenants = await listMyTenants()
    localStorage.setItem('grt_user', JSON.stringify(user.value))
  } catch (e) { ElMessage.error(e.message) }
}
function enterEnterprise(payload) {
  localStorage.setItem('grt_user', JSON.stringify(payload))
  localStorage.setItem('grt_tenant_id', payload.tenant.id)
  sessionStorage.setItem('grt_tenant_picked', '1')
  location.assign('/home')
}
function enterpriseUpdated(info) {
  if (user.value?.tenant) user.value.tenant.name = info.name
  const item = user.value?.tenants?.find(t => t.id === info.id)
  if (item) item.name = info.name
  localStorage.setItem('grt_user', JSON.stringify(user.value))
  pollTenant()
}
async function switchWorkspace(tenantId) {
  let overlay = null
  try {
    const payload = await switchTenant(tenantId)
    localStorage.setItem('grt_user', JSON.stringify(payload))
    localStorage.setItem('grt_tenant_id', payload.tenant?.id || tenantId)
    // 整页 reload 前给过渡提示（reload 本身不可省：各页状态需要彻底重置）
    overlay = ElLoading.service({ text: `正在切换到「${payload.tenant?.name || '新空间'}」…`, background: 'rgba(255,255,255,.85)' })
    sessionStorage.setItem('grt_tenant_picked', '1')
    location.assign('/home')
  } catch (e) {
    overlay?.close()
    ElMessage.error(e.message)
  }
}

async function pollTenant() {
  try {
    tenantInfo.value = await getCurrentTenant()
  } catch { /* 静默：后端未启动或权限不足 */ }
}

// 订阅横幅：可关闭（本次会话不再提示，会话外仍按状态提醒）
function bannerHidden(kind) {
  return sessionStorage.getItem(`grt_banner_hide_${kind}`) === '1'
}
function hideBanner(kind) {
  sessionStorage.setItem(`grt_banner_hide_${kind}`, '1')
  // 触发响应式刷新（tenantInfo 不变，仅显示逻辑依赖 sessionStorage）
  tenantInfo.value = { ...tenantInfo.value }
}

// 修改密码
const pwdVisible = ref(false)
const pwdSaving = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '新密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [{
    validator: (r, v, cb) => {
      if (!v) cb(new Error('请再次输入新密码'))
      else if (v !== pwdForm.new_password) cb(new Error('两次输入的新密码不一致'))
      else cb()
    },
    trigger: 'blur',
  }],
}
// 密码强度：长度 + 字符种类（弱/中/强）
const pwdStrength = computed(() => {
  const p = pwdForm.new_password || ''
  let kinds = 0
  if (/[a-zA-Z]/.test(p)) kinds++
  if (/\d/.test(p)) kinds++
  if (/[^a-zA-Z0-9]/.test(p)) kinds++
  if (p.length >= 10 && kinds >= 3) return { text: '强', cls: 'st-strong' }
  if (p.length >= 8 && kinds >= 2) return { text: '中', cls: 'st-medium' }
  return { text: '弱', cls: 'st-weak' }
})

async function changePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  pwdSaving.value = true
  try {
    await changePasswordApi(pwdForm.old_password, pwdForm.new_password)
    ElMessage.success('密码已修改')
    pwdVisible.value = false
    Object.assign(pwdForm, { old_password: '', new_password: '', confirm: '' })
    pwdFormRef.value?.resetFields()
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
  if (localStorage.getItem('grt_token')) {
    pollUnread()
    pollTenant()
  }
  // 通知页标记已读后广播此事件，角标立即刷新
  window.addEventListener('grt-notify-refresh', pollUnread)
  // 基础设置改名等场景广播此事件，顶栏空间名/角色标签即时刷新（无需整页 reload）
  window.addEventListener('grt-user-refresh', onUserRefresh)
  timer = setInterval(() => {
    if (localStorage.getItem('grt_token')) pollUnread()
  }, 30000)
})
function onUserRefresh() {
  user.value = readUser()
}

onUnmounted(() => {
  window.removeEventListener('grt-user-refresh', onUserRefresh)
  clearInterval(timer)
  window.removeEventListener('grt-notify-refresh', pollUnread)
})
</script>

<style>
:root {
  /* 品牌色变量：全站统一引用，不再各自硬编码 */
  --grt-primary: #409eff;              /* 主色（Element 默认蓝） */
  --grt-ai: #7c5cff;                   /* AI 相关统一紫 */
  --grt-ai-hover: #6848e0;
  --grt-ai-disabled: #b5a3f5;
}
body { margin: 0; font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; }
.layout { height: 100vh; --chrome-h: 48px; }
/* 专注模式：隐藏 chrome（侧边导航/顶栏/订阅横幅），页面高度变量归零 */
.layout.focus { --chrome-h: 0px; }
.layout.focus .aside, .layout.focus .topbar, .layout.focus .sub-banner { display: none; }
.aside { border-right: 1px solid #dce5ef; background: linear-gradient(180deg, #edf5ff 0%, #e8f0fa 100%); transition: width .18s ease; display: flex; flex-direction: column; overflow: hidden; }
.logo { padding: 18px 20px; font-size: 17px; font-weight: 600; color: #303133; white-space: nowrap; overflow: hidden; flex-shrink: 0; }
.nav-brand { display: flex; align-items: center; gap: 9px; height: 64px; padding: 0 14px; box-sizing: border-box; text-decoration: none; flex-shrink: 0; }
.nav-brand-mark { width: 32px; height: 32px; flex-shrink: 0; filter: drop-shadow(0 3px 5px #235bb51a); }
.nav-brand-name { color: #24476d; font-size: 15px; font-weight: 650; white-space: nowrap; }
.aside.nav-compact .nav-brand { justify-content: center; padding: 0; }
.aside .el-menu { border-right: none; background: transparent; flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: 0 5px 8px; scrollbar-width: thin; scrollbar-color: #b8c9dc transparent; }
.aside .el-menu-item { position: relative; height: 44px; line-height: 18px; padding: 0 12px !important; margin: 2px 0; border-radius: 7px; display: flex; align-items: center; gap: 10px; color: #627a96; }
.aside .el-menu-item .el-icon { margin: 0; width: 20px; height: 20px; font-size: 20px; color: #8093a9; }
.aside .el-menu-item > span:not(.menu-unread) { font-size: 13px; line-height: 18px; white-space: nowrap; }
.aside.nav-compact .el-menu-item { height: 50px; flex-direction: column; justify-content: center; gap: 3px; padding: 4px 0 !important; }
.aside.nav-compact .el-menu-item > span:not(.menu-unread) { font-size: 12px; line-height: 16px; }
.aside .el-menu-item:hover { background: #dfeafb; color: #2b70cf; }
.aside .el-menu-item.is-active { background: #d2e5ff; color: #2378ec; font-weight: 600; }
.aside .el-menu-item.is-active .el-icon { color: #2c82f5; }
.aside .el-menu-item:focus-visible, .nav-brand:focus-visible, .collapse-btn:focus-visible { outline: 2px solid #2c82f5; outline-offset: -2px; }
.aside .el-menu-item-group__title { font-size: 0; line-height: 0; padding: 0; margin: 9px 12px; border-top: 1px solid #d4e0ee; }
.collapse-btn { width: 100%; height: 40px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; cursor: pointer; color: #6f87a2; border: 0; border-top: 1px solid #dce5ef; background: transparent; font-size: 17px; }
.collapse-btn:hover { color: #2378ec; background: #dfeafb; }
@media (prefers-reduced-motion: reduce) { .aside { transition: none; } }
.topbar {
  background: #fff; border-bottom: 1px solid #e4e7ed;
  display: flex; align-items: center; justify-content: space-between; height: 48px;
}
.topbar-left { display: flex; align-items: center; gap: 16px; min-width: 0; }
.page-title { font-size: 15px; font-weight: 600; color: #303133; white-space: nowrap; }
.topbar-right { display: flex; align-items: center; gap: 16px; }
.topbar-actions { display: inline-flex; align-items: center; }
.bell-badge { display: inline-flex; cursor: pointer; }
.bell-icon { font-size: 18px; color: #606266; }
.bell-icon:hover { color: var(--grt-primary); }
/* 侧边菜单的未读数角标 */
.menu-unread {
  position: absolute; top: 2px; right: 4px; margin: 0; background: #f56c6c; color: #fff; font-size: 11px; line-height: 1;
  border-radius: 9px; padding: 3px 6px; transform: scale(.9);
}
.user-name { cursor: pointer; font-size: 14px; color: #606266; outline: none; }
.tenant-switcher { width: 180px; }
.sub-banner { height: 32px; }
.pwd-strength { font-size: 12px; color: #909399; margin-top: 4px; line-height: 1.4; }
.pwd-strength-hint { margin-left: 6px; color: #c0c4cc; }
.st-strong { color: #67c23a; font-weight: 600; }
.st-medium { color: #e6a23c; font-weight: 600; }
.st-weak { color: #f56c6c; font-weight: 600; }
.main { background: #f5f7fa; padding: 20px 24px; overflow-y: auto; }
/* flush 页面（编辑器类）：去除内边距，内容贴边 */
.main-flush { padding: 0; }
.focus-icon { font-size: 17px; color: #606266; cursor: pointer; }
.focus-icon:hover { color: var(--grt-primary); }
.focus-exit {
  position: fixed; top: 12px; right: 12px; z-index: 3000;
  width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 50%; cursor: pointer;
  color: #606266; box-shadow: 0 2px 8px rgba(0,0,0,.12);
}
.focus-exit:hover { color: var(--grt-primary); border-color: var(--grt-primary); }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
/* AI 生成按钮：全局统一紫色（.el-button 前缀提权，覆盖 EP 默认色） */
.el-button.ai-btn { background: var(--grt-ai); border-color: var(--grt-ai); color: #fff; }
.el-button.ai-btn:hover, .el-button.ai-btn:focus { background: var(--grt-ai-hover); border-color: var(--grt-ai-hover); color: #fff; }
.el-button.ai-btn.is-disabled, .el-button.ai-btn.is-disabled:hover { background: var(--grt-ai-disabled); border-color: var(--grt-ai-disabled); color: #fff; }
</style>
