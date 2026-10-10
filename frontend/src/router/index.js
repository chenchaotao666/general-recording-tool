import { createRouter, createWebHistory } from 'vue-router'
import TableList from '../views/TableList.vue'
import ImportWizard from '../views/ImportWizard.vue'
import DynamicTable from '../views/DynamicTable.vue'
import Reports from '../views/Reports.vue'
import Settings from '../views/Settings.vue'
import Login from '../views/Login.vue'
import UsersManage from '../views/UsersManage.vue'
import RolesManage from '../views/RolesManage.vue'
import PermissionsManage from '../views/PermissionsManage.vue'
import GroupsManage from '../views/GroupsManage.vue'
import Friends from '../views/Friends.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    // 公开链接分享，免登录（懒加载隔离 echarts 体积）
    { path: '/share/:token', component: () => import('../views/ShareView.vue') },
    // 公开表单（工作流表单触发器），免登录
    { path: '/form/:wfId/:secret', component: () => import('../views/PublicForm.vue') },
    // 免登审批（签名链接），免登录
    { path: '/approve/:token', component: () => import('../views/PublicApprove.vue') },
    { path: '/', redirect: '/home' },
    // 首页工作台：懒加载隔离 grid-layout-plus 体积
    { path: '/home', component: () => import('../views/Home.vue') },
    { path: '/tables', component: TableList },
    { path: '/friends', component: Friends },
    { path: '/import', component: ImportWizard },
    { path: '/t/:id', component: DynamicTable },
    // 懒加载隔离 editorjs 体积
    { path: '/notes', component: () => import('../views/Notes.vue') },
    // 工作流：编辑器懒加载隔离 vue-flow 体积
    { path: '/workflows', component: () => import('../views/Workflows.vue') },
    { path: '/workflows/new', component: () => import('../views/WorkflowEditor.vue') },
    // 旧站内通知里的链接是 /workflows/:id，重定向到编辑器
    { path: '/workflows/:id(\\d+)', redirect: (to) => `/workflows/${to.params.id}/edit` },
    { path: '/workflows/:id/edit', component: () => import('../views/WorkflowEditor.vue') },
    { path: '/workflows/runs/:id', component: () => import('../views/WorkflowRunDetail.vue') },
    { path: '/notifications', component: () => import('../views/Notifications.vue') },
    { path: '/reports', component: Reports },
    // 懒加载隔离 echarts 体积
    { path: '/reports/:id/view', component: () => import('../views/ReportView.vue') },
    // 布局设计器：懒加载隔离 grid-layout-plus 体积
    { path: '/reports/:id/layout', component: () => import('../views/ReportLayoutDesigner.vue') },
    { path: '/settings', component: Settings, meta: { platformAdmin: true } },
    { path: '/billing', component: () => import('../views/Billing.vue') },
    { path: '/members', component: () => import('../views/Members.vue'), meta: { admin: true } },
    { path: '/audit', component: () => import('../views/AuditLogs.vue'), meta: { admin: true } },
    { path: '/system/users', component: UsersManage, meta: { platformAdmin: true } },
    { path: '/system/roles', component: RolesManage, meta: { platformAdmin: true } },
    { path: '/system/permissions', component: PermissionsManage, meta: { platformAdmin: true } },
    { path: '/platform/tenants', component: () => import('../views/PlatformTenants.vue'), meta: { platformAdmin: true } },
    { path: '/platform/plans', component: () => import('../views/PlatformPlans.vue'), meta: { platformAdmin: true } },
    { path: '/system/groups', component: GroupsManage },   // 普通成员也可建组（只能加好友为成员）
  ],
})

router.beforeEach((to) => {
  const user = JSON.parse(localStorage.getItem('grt_user') || 'null')
  if (to.path === '/login' || to.path.startsWith('/share/') || to.path.startsWith('/form/')
    || to.path.startsWith('/approve/')) return true
  if (!localStorage.getItem('grt_token')) return '/login'
  if (to.meta.platformAdmin && !user?.is_platform_admin) return '/tables'
  if (to.meta.admin && user?.role !== 'admin') return '/tables'
})

export default router
