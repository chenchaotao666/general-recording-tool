import axios from 'axios'
import { ElMessageBox } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 180000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('grt_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  const tenantId = localStorage.getItem('grt_tenant_id')
  if (tenantId) config.headers['X-Tenant-Id'] = tenantId
  return config
})

http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    if (e.response?.status === 401) {
      localStorage.removeItem('grt_token')
      localStorage.removeItem('grt_user')
      localStorage.removeItem('grt_tenant_id')
      if (location.pathname !== '/login') location.href = '/login'
    }
    const d = e.response?.data?.detail
    const msg = typeof d === 'string' ? d : d?.message || (d ? JSON.stringify(d) : e.message)
    const err = new Error(msg)
    // 配额/订阅类错误带结构化 code，页面可据此弹升级引导（quota_exceeded / tenant_expired / feature_not_available）
    if (d && typeof d === 'object') {
      err.code = d.code
      err.quota = d.quota
      err.feature = d.feature
      err.status = e.response?.status
    }
    return Promise.reject(err)
  }
)

// 配额/订阅错误：弹升级引导（返回 true 表示已处理，调用方别再 toast）
export function handleBillingError(e) {
  if (e?.code !== 'quota_exceeded' && e?.code !== 'tenant_expired' && e?.code !== 'feature_not_available') return false
  ElMessageBox.confirm(`${e.message}。是否前往「套餐与用量」页查看？`, '提示', {
    type: 'warning', confirmButtonText: '前往查看', cancelButtonText: '关闭',
  }).then(() => { location.href = '/billing' }).catch(() => {})
  return true
}

// 登录 / 注册
export const login = (username, password) => http.post('/auth/login', { username, password })
export const register = (username, password) => http.post('/auth/register', { username, password })
export const changePassword = (oldPassword, newPassword) =>
  http.put('/auth/password', { old_password: oldPassword, new_password: newPassword })

// 工作空间（租户）
export const listMyTenants = () => http.get('/tenants/mine')
export const switchTenant = (tenantId) => http.post('/tenants/switch', { tenant_id: tenantId })
export const getCurrentTenant = () => http.get('/tenants/current')
export const upgradeToEnterprise = () => http.post('/tenants/upgrade-to-enterprise')

// 成员管理（当前工作空间）
export const listMembers = () => http.get('/members')
export const listMyInvitations = () => http.get('/members/invitations')
export const inviteMember = (username, role = 'user') => http.post('/members/invite', { username, role })
export const acceptInvitation = (memberId) => http.post(`/members/${memberId}/accept`)
export const setMemberRole = (memberId, role) => http.put(`/members/${memberId}/role`, { role })
export const setMemberOrg = (memberId, departmentId, managerId) =>
  http.put(`/members/${memberId}/org`, { department_id: departmentId, manager_id: managerId })
export const removeMember = (memberId) => http.delete(`/members/${memberId}`)

// 部门树（组织与成员页）
export const listDepartments = () => http.get('/departments')
export const createDepartment = (p) => http.post('/departments', p)
export const updateDepartment = (id, p) => http.put(`/departments/${id}`, p)
export const moveDepartment = (id, parentId) => http.put(`/departments/${id}/move`, { parent_id: parentId })
export const deleteDepartment = (id) => http.delete(`/departments/${id}`)

// 数据范围（角色 × 表 × scope 矩阵，feature_data_scope 闸）
export const getScopes = () => http.get('/scopes')
export const putScope = (roleId, tableId, scope) =>
  http.put('/scopes', { role_id: roleId, table_id: tableId, scope })
export const applyScopePresets = () => http.post('/scopes/apply-presets')

// 记录转移（表主/租户 admin）
export const transferRecords = (tid, recordIds, ownerId) =>
  http.post(`/dyn/${tid}/transfer`, { record_ids: recordIds, owner_id: ownerId })

// 自助计费（选购/下单/模拟支付/订单）
export const billingPlans = () => http.get('/billing/plans')
export const createOrder = (p) => http.post('/billing/orders', p)
export const payOrder = (orderId) => http.post(`/billing/orders/${orderId}/pay`)
export const listOrders = () => http.get('/billing/orders')

// 审计日志（租户 admin + feature_audit）
export const listAuditLogs = (params) => http.get('/audit', { params })

// 平台管理（平台超管）
export const platformListTenants = () => http.get('/platform/tenants')
export const platformCreateTenant = (p) => http.post('/platform/tenants', p)
export const platformSetSubscription = (tenantId, p) => http.put(`/platform/tenants/${tenantId}/subscription`, p)
export const platformListPlans = () => http.get('/platform/plans')
export const platformCreatePlan = (p) => http.post('/platform/plans', p)
export const platformUpdatePlan = (id, p) => http.put(`/platform/plans/${id}`, p)
export const platformSetEntitlements = (id, entitlements) =>
  http.put(`/platform/plans/${id}/entitlements`, { entitlements })

// Excel 导入
export const uploadExcel = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/excel/upload', fd)
}
export const analyzeExcel = (payload) => http.post('/excel/analyze', payload)

// 图片附件
export const uploadImage = (file) => {
  const fd = new FormData()
  fd.append('files', file)
  return http.post('/uploads/image', fd)
}
export const imageUrl = (id) => `/api/uploads/image/${id}?token=${localStorage.getItem('grt_token')}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`

// 数据表
export const listTables = (params) => http.get('/tables', { params })   // params.all=1：admin 返回全部表（配置场景用）
export const getTable = (id) => http.get(`/tables/${id}`)
export const createTable = (payload) => http.post('/tables', payload)
export const updateTable = (id, payload) => http.put(`/tables/${id}`, payload)
export const alterTable = (id, ops) => http.post(`/tables/${id}/alter`, { ops })
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
export const setUserRole = (id, tenantId, role) => http.put(`/users/${id}/role`, { tenant_id: tenantId, role })

// 角色与权限管理（admin）
export const listRoles = () => http.get('/roles')
export const createRole = (p) => http.post('/roles', p)
export const updateRole = (id, p) => http.put(`/roles/${id}`, p)
export const deleteRole = (id) => http.delete(`/roles/${id}`)
export const setRolePermissions = (id, grants) => http.put(`/roles/${id}/permissions`, { grants })
export const listPermissions = () => http.get('/permissions')

// 动态记录
export const listRecords = (tid, params) => http.get(`/dyn/${tid}/records`, { params })
export const createRecord = (tid, data) => http.post(`/dyn/${tid}/records`, data)
export const updateRecord = (tid, rid, data) => http.put(`/dyn/${tid}/records/${rid}`, data)
export const deleteRecord = (tid, rid) => http.delete(`/dyn/${tid}/records/${rid}`)
export const recordExportUrl = (tid, params) => {
  // <a>/window.open 无法带请求头，token 走查询参数；filters 为 JSON 字符串
  const qs = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v != null && v !== ''))
  const token = localStorage.getItem('grt_token') || ''
  return `/api/dyn/${tid}/export?${qs}&token=${encodeURIComponent(token)}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`
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

// 工作流
export const listWorkflows = () => http.get('/workflows')
export const getWorkflow = (id) => http.get(`/workflows/${id}`)
export const createWorkflow = (p) => http.post('/workflows', p)
export const updateWorkflow = (id, p) => http.put(`/workflows/${id}`, p)
export const checkWorkflow = (p) => http.post('/workflows/check', p)   // 保存前体检（不落库）
export const deleteWorkflow = (id) => http.delete(`/workflows/${id}`)
export const toggleWorkflow = (id) => http.post(`/workflows/${id}/toggle`)
export const runWorkflow = (id, params = {}) => http.post(`/workflows/${id}/run`, { params })
export const testRunWorkflow = (id, params = {}, nodeId = null) =>
  http.post(`/workflows/${id}/test-run`, { params, ...(nodeId ? { node_id: nodeId } : {}) })
export const workflowRuns = (id) => http.get(`/workflows/${id}/runs`)
export const getWorkflowRun = (runId) => http.get(`/workflows/runs/${runId}`)
export const approveWorkflowNode = (nodeRunId, approved, comment = '') =>
  http.post(`/workflows/node-runs/${nodeRunId}/approve`, { approved, comment })
export const listPendingApprovals = () => http.get('/workflows/pending-approvals')
export const workflowNodeTypes = () => http.get('/workflows/node-types')
export const aiAssistWorkflow = (description) => http.post('/workflows/ai-assist', { description })
export const aiNodeConfig = (nodeType, description, context) =>
  http.post('/workflows/ai-node-config', { node_type: nodeType, description, ...(context ? { context } : {}) })
export const aiExplainWorkflow = (id) => http.post(`/workflows/${id}/ai-explain`)

// 公开表单（表单触发器，免登录，URL 即凭证）
export const getPublicForm = (wfId, secret) => http.get(`/workflows/form/${wfId}/${secret}`)
export const submitPublicForm = (wfId, secret, data) => http.post(`/workflows/form/${wfId}/${secret}`, data)

// 免登审批（签名链接）
export const getPublicApproval = (token) => http.get(`/workflows/approval/${token}`)
export const submitPublicApproval = (token, approved, comment = '') =>
  http.post(`/workflows/approval/${token}`, { approved, comment })

// 工作流模板市场
export const listWorkflowTemplates = () => http.get('/workflow-templates')
export const installWorkflowTemplate = (key, withDemoData = false) =>
  http.post(`/workflow-templates/${key}/install`, { with_demo_data: withDemoData })

// MCP 接入
export const getMcpConfig = () => http.get('/mcp/config')
export const createMcpToken = () => http.post('/mcp/token')
export const revokeMcpToken = () => http.delete('/mcp/token')

// 报表
export const listReports = () => http.get('/reports')
export const getReport = (id) => http.get(`/reports/${id}`)
export const createReport = (p) => http.post('/reports', p)
export const updateReport = (id, p) => http.put(`/reports/${id}`, p)
export const deleteReport = (id) => http.delete(`/reports/${id}`)
export const duplicateReport = (id) => http.post(`/reports/${id}/duplicate`)
export const toggleReport = (id) => http.post(`/reports/${id}/toggle`)
export const listReportTemplates = () => http.get('/report-templates')
export const installReportTemplate = (key, withDemoData) => http.post(`/report-templates/${key}/install`, { with_demo_data: withDemoData })
export const runReport = (id, range, filters, links, draft, blockPages, blockOverrides) =>
  http.post(`/reports/${id}/run`, { range, filters, links, draft, block_pages: blockPages, block_overrides: blockOverrides })
export const checkExpr = (p) => http.post('/reports/expr-check', p)
export const drillReport = (id, payload) => http.post(`/reports/${id}/drill`, payload)
export const aiAssistReport = (tableId, description, append = false) =>
  http.post('/reports/ai-assist', { table_id: tableId, description, append })
export const aiAssistBlock = (blockType, description, fields, current) =>
  http.post('/reports/ai-block-config', { block_type: blockType, description, fields, current })
export const testPushReport = (id) => http.post(`/reports/${id}/test-push`)
export const previewPushReport = (id) => http.post(`/reports/${id}/preview-push`)
export const reportRuns = (id) => http.get(`/reports/${id}/runs`)
export const reportExportUrl = (id, params) => {
  // filters 是对象，JSON 序列化后作为查询参数
  const flat = { ...(params || {}) }
  if (flat.filters) flat.filters = JSON.stringify(flat.filters)
  const qs = new URLSearchParams(Object.entries(flat).filter(([, v]) => v != null && v !== ''))
  const token = localStorage.getItem('grt_token') || ''
  return `/api/reports/${id}/export?${qs}&token=${encodeURIComponent(token)}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`
}

// 打印模板（按表共享；view 可见 / owner·admin 可编辑；首次列表后端自动播种预设）
export const listPrintTemplates = (tableId) => http.get(`/tables/${tableId}/print-templates`)
export const createPrintTemplate = (tableId, p) => http.post(`/tables/${tableId}/print-templates`, p)
export const getPrintTemplate = (id) => http.get(`/print-templates/${id}`)
export const updatePrintTemplate = (id, p) => http.put(`/print-templates/${id}`, p)
export const deletePrintTemplate = (id) => http.delete(`/print-templates/${id}`)
export const duplicatePrintTemplate = (id) => http.post(`/print-templates/${id}/duplicate`)
export const setDefaultPrintTemplate = (id) => http.post(`/print-templates/${id}/set-default`)
// Excel 模板：上传用 multipart；下载/填充走 window.open（URL 带 token，同导出 Excel 模式）
export const uploadPrintExcel = (id, file) => {
  const fd = new FormData()
  fd.append('file', file)
  return http.post(`/print-templates/${id}/excel`, fd)
}
// 浏览器内编辑器（luckysheet）保存：表格 JSON → 后端还原 xlsx
export const savePrintExcelJson = (id, sheets) =>
  http.post(`/print-templates/${id}/excel-json`, { sheets }, { timeout: 60000 })
// 模板图片注入：luckyexcel 解析不了 openpyxl 写的图片，由后端直接返回（含像素位置）
export const getPrintExcelImages = (id) => http.get(`/print-templates/${id}/excel-images`)
// 编辑器内容即时预览：表格 JSON + 当前筛选口径 → 填充 HTML（paper 同打印预览）
export const previewPrintExcel = (tableId, sheets, paper = 'a4', params = {}) =>
  http.post(`/tables/${tableId}/print-templates/preview-fill`,
    { sheets, paper, ...params }, { timeout: 120000 })
const _withToken = (path, params) => {
  const flat = { ...(params || {}) }
  const qs = new URLSearchParams(Object.entries(flat).filter(([, v]) => v != null && v !== ''))
  const token = localStorage.getItem('grt_token') || ''
  const sep = qs.size ? '&' : ''
  return `/api/print-templates/${path}?${qs}${sep}token=${encodeURIComponent(token)}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`
}
export const printStarterUrl = (tableId) => {
  // starter 在 /tables 命名空间下，不走 _withToken 的 print-templates 前缀
  const token = localStorage.getItem('grt_token') || ''
  return `/api/tables/${tableId}/print-templates/starter?token=${encodeURIComponent(token)}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`
}
export const printExcelUrl = (id) => _withToken(`${id}/excel`)
export const printFillUrl = (id, params) => _withToken(`${id}/fill`, params)
export const printFillViewUrl = (id, params) => _withToken(`${id}/fill-view`, params)
// 模板库（docs/打印模板 样例）：列表 + xlsx 文件下载
// 对照预览图是静态资源（public/print-library/，与 xlsx 同行业目录同名 jpg），前端直接拼 URL
export const listPrintLibrary = () => http.get('/print-templates/library')
export const printLibraryFileUrl = (path) =>
  _withToken(`library/file`, { path })
export const printLibraryImgUrl = (img) =>
  '/print-library/' + img.split('/').map(encodeURIComponent).join('/')

// 记事本
export const noteTree = () => http.get('/notes/tree')
export const searchNotes = (keyword) => http.get('/notes/search', { params: { keyword } })
export const createNote = (p) => http.post('/notes', p)
export const getNote = (id) => http.get(`/notes/${id}`)
export const updateNote = (id, p) => http.put(`/notes/${id}`, p)
export const deleteNote = (id) => http.delete(`/notes/${id}`)
export const noteAiAssist = (p) => http.post('/notes/ai-assist', p)

// 站内通知
export const listNotifications = () => http.get('/notify')
export const listNotificationsPage = (params) => http.get('/notify/page', { params })
export const unreadCount = () => http.get('/notify/unread_count')

// 首页工作台布局（每用户一份；GET 无记录时返回系统默认布局）
export const getHomeLayout = () => http.get('/home-layout')
export const saveHomeLayout = (layout) => http.put('/home-layout', { layout })
export const deleteHomeLayout = () => http.delete('/home-layout')   // 恢复默认（删除用户布局）
// 管理员：全员默认布局（对没有自己布局的用户生效）
export const saveDefaultHomeLayout = (layout) => http.put('/home-layout/default', { layout })
export const deleteDefaultHomeLayout = () => http.delete('/home-layout/default')
export const markRead = (payload) => http.post('/notify/read', payload)
export const deleteNotifications = (payload) => http.post('/notify/delete', payload)

// 通用设置（SMTP/短信网关）
export const getGeneralSettings = () => http.get('/settings/general')
export const saveGeneralSettings = (p) => http.put('/settings/general', p)
export const testEmail = (to) => http.post('/settings/general/test-email', { to })

// AI 助手
export const assistantChat = (payload) => http.post('/assistant/chat', payload)
export const assistantExecute = (payload) => http.post('/assistant/execute', payload)
export const assistantDownloadUrl = (fileId) => {
  const token = localStorage.getItem('grt_token') || ''
  return `/api/assistant/download/${fileId}?token=${encodeURIComponent(token)}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`
}
export const testSearchSettings = () => http.post('/settings/general/test-search')
