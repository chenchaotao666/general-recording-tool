// 首页卡片类型注册表（插件机制）：新功能注册一条即出现在「添加卡片」选择器里。
// 设计见 docs/首页工作台设计.md
import { markRaw } from 'vue'
import {
  AlarmClock, Avatar, Bell, Connection, DataAnalysis, Grid, Key, List, Menu, Notebook, Setting, Upload, User, UserFilled, Wallet,
} from '@element-plus/icons-vue'

import TableCard from './cards/TableCard.vue'
import TableListCard from './cards/TableListCard.vue'
import MenuCard from './cards/MenuCard.vue'
import NotificationsCard from './cards/NotificationsCard.vue'
import TodosCard from './cards/TodosCard.vue'
import ReportCard from './cards/ReportCard.vue'

const _types = new Map()

export function registerCardType(def) {
  _types.set(def.type, { ...def, component: markRaw(def.component) })
}

export function getCardType(type) {
  return _types.get(type) || null
}

export function listCardTypes() {
  return [..._types.values()]
}

// 菜单功能卡片的可选入口（与 App.vue 侧边栏一致；adminOnly=租户管理员可见，platformOnly=平台超管可见）
export const MENU_ENTRIES = [
  { path: '/tables', title: '数据表', icon: Grid, desc: '我的数据表列表' },
  { path: '/import', title: '导入 Excel', icon: Upload, desc: '从 Excel 建表' },
  { path: '/notes', title: '记事本', icon: Notebook, desc: '笔记与文档' },
  { path: '/reports', title: '报表', icon: DataAnalysis, desc: '报表模板与查看' },
  { path: '/workflows', title: '工作流', icon: Connection, desc: '自动化流程' },
  { path: '/notifications', title: '通知', icon: Bell, desc: '站内通知' },
  { path: '/friends', title: '好友', icon: User, desc: '好友与分享' },
  { path: '/system/groups', title: '用户组', icon: UserFilled, desc: '用户组管理' },
  { path: '/billing', title: '套餐与用量', icon: Wallet, desc: '当前套餐与配额用量' },
  { path: '/members', title: '成员', icon: UserFilled, desc: '工作空间成员（管理员）', adminOnly: true },
  { path: '/audit', title: '审计日志', icon: Key, desc: '操作审计（管理员）', adminOnly: true },
  { path: '/settings', title: '设置', icon: Setting, desc: '实例设置（平台超管）', platformOnly: true },
  { path: '/platform/tenants', title: '平台租户', icon: User, desc: '租户与订阅（平台超管）', platformOnly: true },
  { path: '/platform/plans', title: '套餐配置', icon: Key, desc: '套餐与定价（平台超管）', platformOnly: true },
  { path: '/system/users', title: '用户管理', icon: User, desc: '系统用户（平台超管）', platformOnly: true },
  { path: '/system/roles', title: '角色管理', icon: Avatar, desc: '角色与权限（平台超管）', platformOnly: true },
]

export function menuEntriesFor(user) {
  return MENU_ENTRIES.filter((e) => {
    if (e.platformOnly) return !!user?.is_platform_admin
    if (e.adminOnly) return user?.role === 'admin'
    return true
  })
}

// ---------- 内置类型注册 ----------
// accent：类型色调（柔色底/主色），添加卡片对话框与卡片图标统一使用
registerCardType({
  type: 'table', name: '数据表', desc: '指定一张表的快捷入口（名称/记录数）',
  icon: Grid, accent: { bg: '#e8f3ff', fg: '#409eff' },
  component: TableCard, needConfig: true,
})
registerCardType({
  type: 'table-list', name: '数据表列表', desc: '我的数据表清单（自动更新）',
  icon: List, accent: { bg: '#e8f3ff', fg: '#409eff' },
  component: TableListCard, defaultConfig: { limit: 6 },
})
registerCardType({
  type: 'menu', name: '菜单功能', desc: '系统功能入口（导入/报表/工作流…）',
  icon: Menu, accent: { bg: '#e6f7f6', fg: '#13c2c2' },
  component: MenuCard, needConfig: true,
})
registerCardType({
  type: 'notifications', name: '通知', desc: '最近站内通知与未读数',
  icon: Bell, accent: { bg: '#fdeaea', fg: '#f56c6c' },
  component: NotificationsCard, defaultConfig: { limit: 5 },
})
registerCardType({
  type: 'todos', name: '待办', desc: '我的待审批事项',
  icon: AlarmClock, accent: { bg: '#fdf3e3', fg: '#e6a23c' },
  component: TodosCard, defaultConfig: { limit: 5 },
})
registerCardType({
  type: 'report', name: '报表', desc: '报表区块迷你展示（统计卡/图表等）',
  icon: DataAnalysis, accent: { bg: '#f4ecf7', fg: '#9b59b6' },
  component: ReportCard, needConfig: true,
})
