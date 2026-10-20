import { createRouter, createWebHistory } from 'vue-router'
import TableList from '../views/TableList.vue'
import ImportWizard from '../views/ImportWizard.vue'
import DynamicTable from '../views/DynamicTable.vue'
import Reports from '../views/Reports.vue'
import Settings from '../views/Settings.vue'
import Login from '../views/Login.vue'
import UsersManage from '../views/UsersManage.vue'
import GroupsManage from '../views/GroupsManage.vue'
import Friends from '../views/Friends.vue'
import TenantSelect from '../views/TenantSelect.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    ...['/settings/basic', '/members', '/audit', '/system/roles'].map(path => ({ path, redirect: '/home' })),
    // 登录后选择公司（多工作空间账号）
    { path: '/select-tenant', component: TenantSelect },
    // 公开链接分享，免登录（懒加载隔离 echarts 体积）
    { path: '/share/:token', component: () => import('../views/ShareView.vue') },
    // 公开表单（工作流表单触发器），免登录
    { path: '/form/:wfId/:secret', component: () => import('../views/PublicForm.vue') },
    // 智能表公开表单（分享链接），免登录
    { path: '/sf/:token', component: () => import('../views/smart/PublicSmartForm.vue'), meta: { public: true } },
    // 免登审批（签名链接），免登录
    { path: '/approve/:token', component: () => import('../views/PublicApprove.vue') },
    { path: '/', redirect: '/home' },
    // 首页工作台：懒加载隔离 grid-layout-plus 体积
    { path: '/home', component: () => import('../views/Home.vue'), meta: { title: '首页' } },
    { path: '/tables', component: TableList , meta: { perm: 'menu_tables', title: '数据表' } },
    // 智能表（智慧表格）：条目树首页 + 网格页 + 仪表盘
    { path: '/smart', component: () => import('../views/smart/SmartHome.vue'), meta: { perm: 'menu_smart_tables', title: '智能表', flush: true }, children: [
      { path: 'table/:tableId', component: () => import('../views/smart/SmartTablePage.vue') },
      { path: 'dashboard/:entryId', component: () => import('../views/smart/SmartDashboardPage.vue'), meta: { title: '仪表盘' } },
    ] },
    // vxe-table spike（V1 技术验证页，mock 数据不依赖后端）
    { path: '/smart/spike', component: () => import('../views/smart/SpikeGrid.vue'), meta: { perm: 'menu_smart_tables', title: '智能表-Spike' } },
    { path: '/friends', component: Friends , meta: { perm: 'menu_friends', title: '好友' } },
    { path: '/import', component: ImportWizard , meta: { perm: 'menu_import', title: '导入 Excel' } },
    { path: '/t/:id', component: DynamicTable, meta: { title: '数据表详情' } },
    // 思维导图：懒加载隔离两个引擎的体积
    // 思维导图：目录树 + 嵌入编辑器（与记事本/画板同款布局）；/mindmaps/:id 旧链接重定向到 ?id=
    { path: '/mindmaps', component: () => import('../views/MindMaps.vue'), meta: { perm: 'menu_mindmaps', title: '思维导图', flush: true } },
    { path: '/mindmaps/:id', redirect: (to) => ({ path: '/mindmaps', query: { id: to.params.id } }) },   // 不用正则参数：vue-router 4.6 对 :id(\d+) 不匹配
    // 懒加载隔离富文本编辑器（wangEditor）体积
    { path: '/notes', component: () => import('../views/Notes.vue') , meta: { perm: 'menu_notes', title: '记事本', flush: true } },
    // 画板：懒加载隔离 React 白板（excalidraw/tldraw）体积
    { path: '/whiteboard', component: () => import('../views/Whiteboards.vue'), meta: { perm: 'menu_whiteboard', title: '画板', flush: true } },
    // /studio 是曾经合并入口的临时路径，已拆回两个菜单；旧链接按 tab 参数分流
    { path: '/studio', redirect: (to) => ({ path: to.query.tab === 'boards' ? '/whiteboard' : '/notes', query: Object.fromEntries(Object.entries(to.query).filter(([k]) => k !== 'tab')) }) },
    // 工作流：编辑器懒加载隔离 vue-flow 体积
    { path: '/workflows', component: () => import('../views/Workflows.vue') , meta: { perm: 'menu_workflows', title: '工作流' } },
    { path: '/workflows/new', component: () => import('../views/WorkflowEditor.vue'), meta: { title: '工作流编辑器' } },
    // 旧站内通知里的链接是 /workflows/:id，重定向到编辑器
    { path: '/workflows/:id', redirect: (to) => `/workflows/${to.params.id}/edit` },   // 正则参数在 vue-router 4.6 不匹配，改普通参数
    { path: '/workflows/:id/edit', component: () => import('../views/WorkflowEditor.vue'), meta: { title: '工作流编辑器' } },
    { path: '/workflows/runs/:id', component: () => import('../views/WorkflowRunDetail.vue'), meta: { title: '执行详情' } },
    { path: '/notifications', component: () => import('../views/Notifications.vue') , meta: { perm: 'menu_notifications', title: '通知' } },
    { path: '/reports', component: Reports , meta: { perm: 'menu_reports', title: '报表' } },
    // 懒加载隔离 echarts 体积
    { path: '/reports/:id/view', component: () => import('../views/ReportView.vue'), meta: { title: '报表查看' } },
    // 布局设计器：懒加载隔离 grid-layout-plus 体积
    { path: '/reports/:id/layout', component: () => import('../views/ReportLayoutDesigner.vue'), meta: { title: '报表设计器' } },
    { path: '/settings', component: Settings, meta: { platformAdmin: true, title: '集成设置' } },
    // 系统设置-基础设置：租户 admin 维护公司名称
    { path: '/billing', component: () => import('../views/Billing.vue') , meta: { perm: 'menu_billing', title: '套餐与用量' } },
    { path: '/billing/upgrade', component: () => import('../views/Upgrade.vue'), meta: { admin: true, title: '升级套餐' } },
    { path: '/system/users', component: UsersManage, meta: { platformAdmin: true, title: '用户管理' } },
    { path: '/platform/tenants', component: () => import('../views/PlatformTenants.vue'), meta: { platformAdmin: true, title: '平台租户' } },
    { path: '/platform/plans', component: () => import('../views/PlatformPlans.vue'), meta: { platformAdmin: true, title: '套餐配置' } },
    { path: '/system/groups', component: GroupsManage, meta: { perm: 'menu_groups', title: '用户组' } },   // 普通成员也可建组（只能加好友为成员）
  ],
})

router.beforeEach((to) => {
  const user = JSON.parse(localStorage.getItem('grt_user') || 'null')
  if (to.path === '/login' || to.path.startsWith('/share/') || to.path.startsWith('/form/') || to.path.startsWith('/sf/')
    || to.path.startsWith('/approve/')) return true
  if (!localStorage.getItem('grt_token')) return '/login'
  // 多空间账号：每个浏览器会话进入主界面前先选公司（选择动作会写 sessionStorage 标记）
  if (to.path !== '/select-tenant' && (user?.tenants?.length || 0) > 1
      && !sessionStorage.getItem('grt_tenant_picked')) return '/select-tenant'
  if (to.meta.platformAdmin && !user?.is_platform_admin) return '/tables'
  if (to.meta.admin && user?.role !== 'admin') return '/tables'
  // 菜单功能权限：perms 缺失（老会话）时放行；admin 恒有全部
  if (to.meta.perm && user?.role !== 'admin' && Array.isArray(user?.perms)
      && !user.perms.includes(to.meta.perm)) return '/home'
})

export default router
