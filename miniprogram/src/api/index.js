import { BASE_URL } from '../config'

// 登录态：token 存本地，所有请求带 Authorization；401 时清 token 回登录页
function authHeader() {
  const token = uni.getStorageSync('grt_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function toLogin() {
  uni.removeStorageSync('grt_token')
  uni.removeStorageSync('grt_user')
  const pages = getCurrentPages()
  const cur = pages[pages.length - 1]
  if (cur && cur.route === 'pages/login/index') return  // 已在登录页（如密码错误）不再跳转
  uni.reLaunch({ url: '/pages/login/index' })
}

// uni.request 封装：统一 baseURL、错误提示，resolve 业务数据
function request(method, url, data) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + '/api' + url,
      method,
      data,
      header: authHeader(),
      timeout: 180000,
      success: (res) => {
        if (res.statusCode === 401) {
          toLogin()
          reject(new Error(res.data?.detail || '未登录或登录已过期'))
        } else if (res.statusCode >= 200 && res.statusCode < 300) {
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

// 登录/注册（不经过 request 的 401 跳转，失败时停留在登录页提示）
function authPost(url, data) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + url,
      method: 'POST',
      data,
      timeout: 10000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(new Error(res.data?.detail || `请求失败（${res.statusCode}）`))
        }
      },
      fail: () => reject(new Error('无法连接服务器，请检查网络')),
    })
  })
}
export const login = (username, password) => authPost('/api/auth/login', { username, password })
export const register = (username, password) => authPost('/api/auth/register', { username, password })
export const changePassword = (oldPassword, newPassword) =>
  http.put('/auth/password', { old_password: oldPassword, new_password: newPassword })

// 数据表
export const listTables = () => http.get('/tables')
export const getTable = (id) => http.get(`/tables/${id}`)
export const createTable = (payload) => http.post('/tables', payload)
export const deleteTable = (id) => http.del(`/tables/${id}`)

// 表分享（vip/admin）
export const listShares = (tid) => http.get(`/tables/${tid}/shares`)
export const putShare = (tid, payload) => http.post(`/tables/${tid}/shares`, payload)
export const deleteShare = (tid, sid) => http.del(`/tables/${tid}/shares/${sid}`)

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
export const deleteFriend = (id) => http.del(`/friends/${id}`)

// 用户搜索 / 我的组
export const searchUsers = (q, scope) => http.get('/users/search', { q, scope })
export const listMyGroups = () => http.get('/groups/mine')

// Excel 导入
export function uploadExcelFile(filePath, fileName) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: BASE_URL + '/api/excel/upload',
      filePath,
      name: 'file',
      header: authHeader(),
      success: (res) => {
        if (res.statusCode === 401) {
          toLogin()
          reject(new Error('未登录或登录已过期'))
          return
        }
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
export const runReport = (id, range, filters) => http.post(`/reports/${id}/run`, { range, filters })
export const drillReport = (id, payload) => http.post(`/reports/${id}/drill`, payload)

// 站内通知
export const listNotifications = () => http.get('/notify')
export const unreadCount = () => http.get('/notify/unread_count')
export const markRead = (payload) => http.post('/notify/read', payload)

// 微信小程序 wx.uploadFile 不支持 files 多文件参数（仅 App/H5 支持），
// 这里手动拼接 multipart/form-data 二进制体，用 uni.request 一次上传多图
function utf8Bytes(str) {
  const encoded = encodeURIComponent(str)
  const bytes = []
  for (let i = 0; i < encoded.length; i++) {
    if (encoded[i] === '%') {
      bytes.push(parseInt(encoded.slice(i + 1, i + 3), 16))
      i += 2
    } else {
      bytes.push(encoded.charCodeAt(i))
    }
  }
  return new Uint8Array(bytes)
}

function buildMultipartBody(filePaths, fields) {
  const boundary = '----formdata' + Date.now().toString(16) + Math.random().toString(16).slice(2)
  const fsm = uni.getFileSystemManager()
  const chunks = []
  const push = (data) => chunks.push(typeof data === 'string' ? utf8Bytes(data) : new Uint8Array(data))
  const NL = '\r\n'

  for (const [k, v] of Object.entries(fields)) {
    push(`--${boundary}${NL}Content-Disposition: form-data; name="${k}"${NL}${NL}${v}${NL}`)
  }

  let chain = Promise.resolve()
  filePaths.forEach((p, i) => {
    chain = chain.then(() => new Promise((res, rej) => {
      push(`--${boundary}${NL}Content-Disposition: form-data; name="images"; filename="image_${i + 1}.jpg"${NL}Content-Type: image/jpeg${NL}${NL}`)
      fsm.readFile({
        filePath: p,
        success: (r) => { push(r.data); push(NL); res() },
        fail: rej,
      })
    }))
  })

  return chain.then(() => {
    push(`--${boundary}--${NL}`)
    const body = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0))
    let offset = 0
    for (const c of chunks) { body.set(c, offset); offset += c.length }
    return { body: body.buffer, contentType: `multipart/form-data; boundary=${boundary}` }
  })
}

// 图片识别填表（上传走 uni.request 手动拼 multipart，多图同名 images）
export function recognizeVision(tableId, filePaths, current, recordId) {
  return buildMultipartBody(filePaths, {
    table_id: String(tableId),
    current: JSON.stringify(current || {}),
    ...(recordId ? { record_id: String(recordId) } : {}),
  }).then(({ body, contentType }) => new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + '/api/vision/recognize',
      method: 'POST',
      header: { 'Content-Type': contentType, ...authHeader() },
      data: body,
      timeout: 180000,
      success: (res) => {
        if (res.statusCode === 401) {
          toLogin()
          reject(new Error('未登录或登录已过期'))
          return
        }
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
  }))
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
