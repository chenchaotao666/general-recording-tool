<template>
  <!-- 裸页（不带侧边菜单壳）：登录、登录后的选择公司、公开分享/表单/审批 -->
  <router-view v-if="$route.path === '/login' || $route.path === '/select-tenant'
    || $route.path.startsWith('/share/') || $route.path.startsWith('/form/') || $route.path.startsWith('/approve/')" />
  <el-container v-else class="layout">
    <el-aside :width="navCollapsed ? '64px' : '200px'" class="aside">
      <div class="logo" :title="navCollapsed ? '通用记录工具' : ''">{{ navCollapsed ? '记' : '通用记录工具' }}</div>
      <el-menu :default-active="$route.path" router :collapse="navCollapsed" :collapse-transition="false">
        <el-menu-item index="/home">
          <el-icon><HomeFilled /></el-icon><span>首页</span>
        </el-menu-item>
        <el-menu-item-group>
          <template #title>工作区</template>
          <el-menu-item v-if="hasMenu('menu_tables')" index="/tables">
            <el-icon><Grid /></el-icon><span>数据表</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_import')" index="/import">
            <el-icon><Upload /></el-icon><span>导入 Excel</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_notes')" index="/notes">
            <el-icon><Notebook /></el-icon><span>记事本</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_reports')" index="/reports">
            <el-icon><DataAnalysis /></el-icon><span>报表</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_workflows')" index="/workflows">
            <el-icon><Connection /></el-icon><span>工作流</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('menu_mindmaps')" index="/mindmaps">
            <el-icon><Share /></el-icon><span>思维导图</span>
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
        <!-- 多人协作管理仅企业空间需要（个人空间隐藏，设计文档 §0：个人版隐藏协作权限子系统） -->
        <el-menu-item-group v-if="(user?.role === 'admin' && isEnterprise) || showAudit">
          <template #title>管理</template>
          <el-menu-item v-if="user?.role === 'admin' && isEnterprise" index="/members">
            <el-icon><UserFilled /></el-icon><span>组织与成员</span>
          </el-menu-item>
          <el-menu-item v-if="user?.role === 'admin' && isEnterprise" index="/system/roles">
            <el-icon><Avatar /></el-icon><span>角色管理</span>
          </el-menu-item>
          <el-menu-item v-if="showAudit" index="/audit">
            <el-icon><Document /></el-icon><span>审计日志</span>
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
          <el-menu-item v-if="user?.role === 'admin' && user?.tenant" index="/settings/basic">
            <el-icon><OfficeBuilding /></el-icon><span>基础设置</span>
          </el-menu-item>
          <el-menu-item v-if="user?.is_platform_admin" index="/settings">
            <el-icon><Setting /></el-icon><span>集成设置</span>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
      <div class="collapse-btn" :title="navCollapsed ? '展开导航' : '收起导航'" @click="toggleNav">
        <el-icon><Expand v-if="navCollapsed" /><Fold v-else /></el-icon>
      </div>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <span class="page-title">{{ $route.meta.title || '' }}</span>
          <span id="topbarActions" class="topbar-actions" />
        </div>
        <div class="topbar-right">
          <el-badge :value="unread || ''" :max="99" class="bell-badge">
            <el-icon class="bell-icon" title="通知" @click="router.push('/notifications')"><Bell /></el-icon>
          </el-badge>
          <el-select
            v-if="user?.tenants?.length > 1"
            :model-value="user.tenant?.id"
            size="small"
            class="tenant-switcher"
            @change="switchWorkspace"
          >
            <el-option v-for="t in user.tenants" :key="t.id" :value="t.id" :label="t.name" />
          </el-select>
          <el-tag v-else-if="user?.tenant" size="small" effect="plain">{{ user.tenant.name }}</el-tag>
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
import { ElLoading, ElMessage } from 'element-plus'
import { Avatar, Bell, Collection, Connection, DataAnalysis, Document, Expand, Fold, Grid, HomeFilled, Notebook, OfficeBuilding, Postcard, PriceTag, Setting, Share, Upload, User, UserFilled, Wallet } from '@element-plus/icons-vue'
import { changePassword as changePasswordApi, getCurrentTenant, switchTenant, unreadCount } from './api'
import AssistantPanel from './components/AssistantPanel.vue'

const router = useRouter()
const route = useRoute()
const unread = ref(0)
// 侧边导航折叠状态（记住选择）
const navCollapsed = ref(localStorage.getItem('grt_nav_collapsed') === '1')
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
watch(() => route.path, () => {
  user.value = readUser()
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
const isEnterprise = computed(() => user.value?.tenant?.type === 'enterprise')
const showAudit = computed(() => user.value?.role === 'admin' && user.value?.tenant && tenantInfo.value?.entitlements?.feature_audit)
const roleLabel = computed(() => ({ admin: '管理员', vip: 'VIP', user: '普通用户' }[user.value?.role] || user.value?.role || '普通用户'))
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

async function switchWorkspace(tenantId) {
  let overlay = null
  try {
    const payload = await switchTenant(tenantId)
    localStorage.setItem('grt_user', JSON.stringify(payload))
    localStorage.setItem('grt_tenant_id', payload.tenant?.id || tenantId)
    // 整页 reload 前给过渡提示（reload 本身不可省：各页状态需要彻底重置）
    overlay = ElLoading.service({ text: `正在切换到「${payload.tenant?.name || '新空间'}」…`, background: 'rgba(255,255,255,.85)' })
    location.reload()
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
.layout { height: 100vh; }
.aside { border-right: 1px solid #e4e7ed; background: #fafafa; transition: width .15s ease; display: flex; flex-direction: column; }
.logo { padding: 18px 20px; font-size: 17px; font-weight: 600; color: #303133; white-space: nowrap; overflow: hidden; flex-shrink: 0; }
.aside .el-menu { border-right: none; background: transparent; flex: 1; overflow-y: auto; }
.aside .el-menu--collapse { width: 100%; }
/* 分组标题更淡更小，与菜单项拉开层级 */
.aside .el-menu-item-group__title { font-size: 11px; color: #b1b5bd; padding: 10px 20px 2px; }
.collapse-btn {
  height: 40px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  color: #909399; border-top: 1px solid #e4e7ed; background: #fafafa;
}
.collapse-btn:hover { color: var(--grt-primary); background: #f0f2f5; }
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
  margin-left: auto; background: #f56c6c; color: #fff; font-size: 11px; line-height: 1;
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
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
/* AI 生成按钮：全局统一紫色（.el-button 前缀提权，覆盖 EP 默认色） */
.el-button.ai-btn { background: var(--grt-ai); border-color: var(--grt-ai); color: #fff; }
.el-button.ai-btn:hover, .el-button.ai-btn:focus { background: var(--grt-ai-hover); border-color: var(--grt-ai-hover); color: #fff; }
.el-button.ai-btn.is-disabled, .el-button.ai-btn.is-disabled:hover { background: var(--grt-ai-disabled); border-color: var(--grt-ai-disabled); color: #fff; }
</style>
