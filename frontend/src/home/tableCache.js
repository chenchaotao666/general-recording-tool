// 表列表共享缓存：首页多张数据表卡片共用一次请求（30s 内复用）
import { listTables } from '../api'

let _cache = null
let _cacheAt = 0
let _pending = null

export function loadTablesShared(force = false) {
  if (!force && _cache && Date.now() - _cacheAt < 30000) return Promise.resolve(_cache)
  if (_pending) return _pending
  _pending = listTables()
    .then((rows) => { _cache = rows || []; _cacheAt = Date.now(); return _cache })
    .finally(() => { _pending = null })
  return _pending
}
