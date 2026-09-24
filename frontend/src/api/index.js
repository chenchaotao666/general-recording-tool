import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 180000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('grt_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    if (e.response?.status === 401) {
      localStorage.removeItem('grt_token')
      localStorage.removeItem('grt_user')
      if (location.pathname !== '/login') location.href = '/login'
    }
    const d = e.response?.data?.detail
    const msg = typeof d === 'string' ? d : d ? JSON.stringify(d) : e.message
    return Promise.reject(new Error(msg))
  }
)

// 登录 / 注册
export const login = (username, password) => http.post('/auth/login', { username, password })
export const register = (username, password) => http.post('/auth/register', { username, password })
export const changePassword = (oldPassword, newPassword) =>
  http.put('/auth/password', { old_password: oldPassword, new_password: newPassword })

// Excel 导入
export const uploadExcel = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/excel/upload', fd)
}
export const analyzeExcel = (payload) => http.post('/excel/analyze', payload)

// 数据表
export const listTables = () => http.get('/tables')
export const getTable = (id) => http.get(`/tables/${id}`)
export const createTable = (payload) => http.post('/tables', payload)
export const updateTable = (id, payload) => http.put(`/tables/${id}`, payload)
export const deleteTable = (id) => http.delete(`/tables/${id}`)

// 表分享（vip/admin）
export const listShares = (tid) => http.get(`/tables/${tid}/shares`)
export const putShare = (tid, payload) => http.post(`/tables/${tid}/shares`, payload)
export const deleteShare = (tid, sid) => http.delete(`/tables/${tid}/shares/${sid}`)

// 待接受分享（接收者侧）
export const listPendingShares = () => http.get('/shares/pending')
export const acceptShare = (id) => http.post(`/shares/${id}/accept`)
export const rejectShare = (id) => http.post(`/shares/${id}/reject`)

// 好友
export const listFriends = () => http.get('/friends')
export const requestFriend = (username) => http.post('/friends/request', { username })
export const listFriendRequests = () => http.get('/friends/requests')
export const acceptFriend = (id) => http.post(`/friends/${id}/accept`)
export const rejectFriend = (id) => http.post(`/friends/${id}/reject`)
export const deleteFriend = (id) => http.delete(`/friends/${id}`)

// 用户搜索 / 我的组
export const searchUsers = (q, scope) => http.get('/users/search', { params: { q, scope } })
export const listMyGroups = () => http.get('/groups/mine')

// 链接分享
export const listShareLinks = (tid) => http.get(`/tables/${tid}/share-links`)
export const createShareLink = (tid, payload) => http.post(`/tables/${tid}/share-links`, payload)
export const deleteShareLink = (tid, lid) => http.delete(`/tables/${tid}/share-links/${lid}`)
export const listReportShareLinks = (id) => http.get(`/reports/${id}/share-links`)
export const createReportShareLink = (id, payload) => http.post(`/reports/${id}/share-links`, payload)
export const deleteReportShareLink = (id, lid) => http.delete(`/reports/${id}/share-links/${lid}`)

// 用户组（admin）
export const listGroups = () => http.get('/groups')
export const createGroup = (p) => http.post('/groups', p)
export const updateGroup = (id, p) => http.put(`/groups/${id}`, p)
export const deleteGroup = (id) => http.delete(`/groups/${id}`)
export const addGroupMember = (id, username) => http.post(`/groups/${id}/members`, { username })
export const removeGroupMember = (id, uid) => http.delete(`/groups/${id}/members/${uid}`)

// 用户管理（admin）
export const listUsers = () => http.get('/users')
export const setUserRole = (id, role) => http.put(`/users/${id}/role`, { role })

// 角色与权限管理（admin）
export const listRoles = () => http.get('/roles')
export const createRole = (p) => http.post('/roles', p)
export const updateRole = (id, p) => http.put(`/roles/${id}`, p)
export const deleteRole = (id) => http.delete(`/roles/${id}`)
export const setRolePermissions = (id, grants) => http.put(`/roles/${id}/permissions`, { grants })
export const listPermissions = () => http.get('/permissions')
export const createPermission = (p) => http.post('/permissions', p)
export const deletePermission = (id) => http.delete(`/permissions/${id}`)

// 动态记录
export const listRecords = (tid, params) => http.get(`/dyn/${tid}/records`, { params })
export const createRecord = (tid, data) => http.post(`/dyn/${tid}/records`, data)
export const updateRecord = (tid, rid, data) => http.put(`/dyn/${tid}/records/${rid}`, data)
export const deleteRecord = (tid, rid) => http.delete(`/dyn/${tid}/records/${rid}`)
export const recordExportUrl = (tid, params) => {
  // <a>/window.open 无法带请求头，token 走查询参数；filters 为 JSON 字符串
  const qs = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v != null && v !== ''))
  const token = localStorage.getItem('grt_token') || ''
  return `/api/dyn/${tid}/export?${qs}&token=${encodeURIComponent(token)}`
}

// LLM 设置
export const listProviders = () => http.get('/settings/llm')
export const createProvider = (p) => http.post('/settings/llm', p)
export const updateProvider = (id, p) => http.put(`/settings/llm/${id}`, p)
export const deleteProvider = (id) => http.delete(`/settings/llm/${id}`)
export const testProvider = (id) => http.post(`/settings/llm/${id}/test`)
export const setDefaultProvider = (id) => http.post(`/settings/llm/${id}/default`)

// 图片识别填表
export const recognizeForm = (formData) => http.post('/vision/recognize', formData)
export const adoptVision = (logId, adopted) => http.put(`/vision/logs/${logId}/adopt`, { adopted })

// 任务规则
export const listTasks = () => http.get('/tasks')
export const createTask = (p) => http.post('/tasks', p)
export const updateTask = (id, p) => http.put(`/tasks/${id}`, p)
export const deleteTask = (id) => http.delete(`/tasks/${id}`)
export const toggleTask = (id) => http.post(`/tasks/${id}/toggle`)
export const testTask = (id) => http.post(`/tasks/${id}/test`)
export const runTask = (id) => http.post(`/tasks/${id}/run`)
export const taskRuns = (id) => http.get(`/tasks/${id}/runs`)
export const aiAssistTask = (tableId, description) => http.post('/tasks/ai-assist', { table_id: tableId, description })

// 报表
export const listReports = () => http.get('/reports')
export const getReport = (id) => http.get(`/reports/${id}`)
export const createReport = (p) => http.post('/reports', p)
export const updateReport = (id, p) => http.put(`/reports/${id}`, p)
export const deleteReport = (id) => http.delete(`/reports/${id}`)
export const toggleReport = (id) => http.post(`/reports/${id}/toggle`)
export const runReport = (id, range, filters) => http.post(`/reports/${id}/run`, { range, filters })
export const drillReport = (id, payload) => http.post(`/reports/${id}/drill`, payload)
export const aiAssistReport = (tableId, description) => http.post('/reports/ai-assist', { table_id: tableId, description })
export const testPushReport = (id) => http.post(`/reports/${id}/test-push`)
export const reportRuns = (id) => http.get(`/reports/${id}/runs`)
export const reportExportUrl = (id, params) => {
  // filters 是对象，JSON 序列化后作为查询参数
  const flat = { ...(params || {}) }
  if (flat.filters) flat.filters = JSON.stringify(flat.filters)
  const qs = new URLSearchParams(Object.entries(flat).filter(([, v]) => v != null && v !== ''))
  const token = localStorage.getItem('grt_token') || ''
  return `/api/reports/${id}/export?${qs}&token=${encodeURIComponent(token)}`
}

// 站内通知
export const listNotifications = () => http.get('/notify')
export const unreadCount = () => http.get('/notify/unread_count')
export const markRead = (payload) => http.post('/notify/read', payload)

// 通用设置（SMTP/短信网关）
export const getGeneralSettings = () => http.get('/settings/general')
export const saveGeneralSettings = (p) => http.put('/settings/general', p)
export const testEmail = (to) => http.post('/settings/general/test-email', { to })

// AI 助手
export const assistantChat = (payload) => http.post('/assistant/chat', payload)
export const assistantExecute = (payload) => http.post('/assistant/execute', payload)
export const assistantDownloadUrl = (fileId) => {
  const token = localStorage.getItem('grt_token') || ''
  return `/api/assistant/download/${fileId}?token=${encodeURIComponent(token)}`
}
export const testSearchSettings = () => http.post('/settings/general/test-search')
