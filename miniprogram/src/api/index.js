import { BASE_URL } from '../config'

// uni.request 封装：统一 baseURL、错误提示，resolve 业务数据
function request(method, url, data) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + '/api' + url,
      method,
      data,
      timeout: 180000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          const d = res.data?.detail
          const msg = typeof d === 'string' ? d : d ? JSON.stringify(d) : `请求失败（${res.statusCode}）`
          reject(new Error(msg))
        }
      },
      fail: (err) => reject(new Error('无法连接服务器，请确认后端已启动且网络可达')),
    })
  })
}

const http = {
  get: (url, params) => request('GET', url, params),
  post: (url, data) => request('POST', url, data || {}),
  put: (url, data) => request('PUT', url, data || {}),
  del: (url) => request('DELETE', url),
}

// 数据表
export const listTables = () => http.get('/tables')
export const getTable = (id) => http.get(`/tables/${id}`)
export const createTable = (payload) => http.post('/tables', payload)
export const deleteTable = (id) => http.del(`/tables/${id}`)

// Excel 导入
export function uploadExcelFile(filePath, fileName) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: BASE_URL + '/api/excel/upload',
      filePath,
      name: 'file',
      success: (res) => {
        let data = res.data
        if (typeof data === 'string') {
          try { data = JSON.parse(data) } catch { data = {} }
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data)
        } else {
          const d = data?.detail
          reject(new Error(typeof d === 'string' ? d : `上传失败（${res.statusCode}）`))
        }
      },
      fail: () => reject(new Error('上传失败，请检查网络')),
    })
  })
}
export const analyzeExcel = (payload) => http.post('/excel/analyze', payload)

// 动态记录
export const listRecords = (tid, params) => http.get(`/dyn/${tid}/records`, params)
export const getRecord = (tid, rid) => http.get(`/dyn/${tid}/records/${rid}`)
export const createRecord = (tid, data) => http.post(`/dyn/${tid}/records`, data)
export const updateRecord = (tid, rid, data) => http.put(`/dyn/${tid}/records/${rid}`, data)
export const deleteRecord = (tid, rid) => http.del(`/dyn/${tid}/records/${rid}`)

// 任务规则
export const listTasks = () => http.get('/tasks')
export const toggleTask = (id) => http.post(`/tasks/${id}/toggle`)
export const testTask = (id) => http.post(`/tasks/${id}/test`)
export const runTask = (id) => http.post(`/tasks/${id}/run`)
export const taskRuns = (id) => http.get(`/tasks/${id}/runs`)

// 报表
export const listReports = () => http.get('/reports')
export const runReport = (id, range) => http.post(`/reports/${id}/run`, { range })

// 站内通知
export const listNotifications = () => http.get('/notify')
export const unreadCount = () => http.get('/notify/unread_count')
export const markRead = (payload) => http.post('/notify/read', payload)

// 图片识别填表（上传走 uni.uploadFile，多图同名 images）
export function recognizeVision(tableId, filePaths, current, recordId) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: BASE_URL + '/api/vision/recognize',
      files: filePaths.map((p) => ({ name: 'images', uri: p })),
      formData: {
        table_id: tableId,
        current: JSON.stringify(current || {}),
        ...(recordId ? { record_id: recordId } : {}),
      },
      timeout: 180000,
      success: (res) => {
        let data = res.data
        if (typeof data === 'string') {
          try { data = JSON.parse(data) } catch { data = {} }
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data)
        } else {
          const d = data?.detail
          reject(new Error(typeof d === 'string' ? d : `识别失败（${res.statusCode}）`))
        }
      },
      fail: () => reject(new Error('上传失败，请检查网络')),
    })
  })
}
export const adoptVision = (logId, adopted) => http.put(`/vision/logs/${logId}/adopt`, { adopted })

// AI 辅助创建
export const aiAssistTask = (tableId, description) => http.post('/tasks/ai-assist', { table_id: tableId, description })
export const createTask = (p) => http.post('/tasks', p)
export const updateTask = (id, p) => http.put(`/tasks/${id}`, p)
export const aiAssistReport = (tableId, description) => http.post('/reports/ai-assist', { table_id: tableId, description })
export const createReport = (p) => http.post('/reports', p)
export const updateReport = (id, p) => http.put(`/reports/${id}`, p)
export const getReport = (id) => http.get(`/reports/${id}`)

// 模型设置
export const listProviders = () => http.get('/settings/llm')
export const createProvider = (p) => http.post('/settings/llm', p)
export const updateProvider = (id, p) => http.put(`/settings/llm/${id}`, p)
export const deleteProvider = (id) => http.del(`/settings/llm/${id}`)
export const testProvider = (id) => http.post(`/settings/llm/${id}/test`)
export const setDefaultProvider = (id) => http.post(`/settings/llm/${id}/default`)
export const getGeneralSettings = () => http.get('/settings/general')
export const saveGeneralSettings = (p) => http.put('/settings/general', p)
export const testEmail = (to) => http.post('/settings/general/test-email', { to })
