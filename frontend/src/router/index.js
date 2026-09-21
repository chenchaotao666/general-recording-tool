import { createRouter, createWebHistory } from 'vue-router'
import TableList from '../views/TableList.vue'
import ImportWizard from '../views/ImportWizard.vue'
import DynamicTable from '../views/DynamicTable.vue'
import Tasks from '../views/Tasks.vue'
import Settings from '../views/Settings.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/tables' },
    { path: '/tables', component: TableList },
    { path: '/import', component: ImportWizard },
    { path: '/t/:id', component: DynamicTable },
    { path: '/tasks', component: Tasks },
    { path: '/settings', component: Settings },
  ],
})
