import { createRouter, createWebHistory } from 'vue-router'
import TableList from '../views/TableList.vue'
import ImportWizard from '../views/ImportWizard.vue'
import DynamicTable from '../views/DynamicTable.vue'
import Tasks from '../views/Tasks.vue'
import Reports from '../views/Reports.vue'
import Settings from '../views/Settings.vue'
import Login from '../views/Login.vue'
import ShareView from '../views/ShareView.vue'
import UsersManage from '../views/UsersManage.vue'
import RolesManage from '../views/RolesManage.vue'
import PermissionsManage from '../views/PermissionsManage.vue'
import GroupsManage from '../views/GroupsManage.vue'
import Friends from '../views/Friends.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/share/:token', component: ShareView },  // 公开链接分享，免登录
    { path: '/', redirect: '/tables' },
    { path: '/tables', component: TableList },
    { path: '/friends', component: Friends },
    { path: '/import', component: ImportWizard },
    { path: '/t/:id', component: DynamicTable },
    // 懒加载隔离 editorjs 体积
    { path: '/notes', component: () => import('../views/Notes.vue') },
    { path: '/tasks', component: Tasks },
    { path: '/reports', component: Reports },
    // 懒加载隔离 echarts 体积
    { path: '/reports/:id/view', component: () => import('../views/ReportView.vue') },
    { path: '/settings', component: Settings },
    { path: '/system/users', component: UsersManage, meta: { admin: true } },
    { path: '/system/roles', component: RolesManage, meta: { admin: true } },
    { path: '/system/permissions', component: PermissionsManage, meta: { admin: true } },
    { path: '/system/groups', component: GroupsManage, meta: { admin: true } },
  ],
})

router.beforeEach((to) => {
  const user = JSON.parse(localStorage.getItem('grt_user') || 'null')
  if (to.path === '/login' || to.path.startsWith('/share/')) return true
  if (!localStorage.getItem('grt_token')) return '/login'
  if (to.meta.admin && user?.role !== 'admin') return '/tables'
})

export default router
