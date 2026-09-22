import { createRouter, createWebHistory } from 'vue-router'
import TableList from '../views/TableList.vue'
import ImportWizard from '../views/ImportWizard.vue'
import DynamicTable from '../views/DynamicTable.vue'
import Tasks from '../views/Tasks.vue'
import Reports from '../views/Reports.vue'
import Settings from '../views/Settings.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/tables' },
    { path: '/tables', component: TableList },
    { path: '/import', component: ImportWizard },
    { path: '/t/:id', component: DynamicTable },
    { path: '/tasks', component: Tasks },
    { path: '/reports', component: Reports },
    // 懒加载隔离 echarts 体积
    { path: '/reports/:id/view', component: () => import('../views/ReportView.vue') },
    { path: '/settings', component: Settings },
  ],
})
