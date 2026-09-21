import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 180000 })

http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    const d = e.response?.data?.detail
    const msg = typeof d === 'string' ? d : d ? JSON.stringify(d) : e.message
    return Promise.reject(new Error(msg))
  }
)

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

// 动态记录
export const listRecords = (tid, params) => http.get(`/dyn/${tid}/records`, { params })
export const createRecord = (tid, data) => http.post(`/dyn/${tid}/records`, data)
export const updateRecord = (tid, rid, data) => http.put(`/dyn/${tid}/records/${rid}`, data)
export const deleteRecord = (tid, rid) => http.delete(`/dyn/${tid}/records/${rid}`)

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

// 站内通知
export const listNotifications = () => http.get('/notify')
export const unreadCount = () => http.get('/notify/unread_count')
export const markRead = (payload) => http.post('/notify/read', payload)

// 通用设置（SMTP/短信网关）
export const getGeneralSettings = () => http.get('/settings/general')
export const saveGeneralSettings = (p) => http.put('/settings/general', p)
export const testEmail = (to) => http.post('/settings/general/test-email', { to })
