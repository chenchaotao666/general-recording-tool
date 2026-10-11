/** 时间格式化工具：全站统一。后端时间是本地时区 'YYYY-MM-DD HH:mm:ss'（naive，无时区）。 */

function parse(s) {
  if (!s) return null
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return null
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0))
}

const p2 = (n) => String(n).padStart(2, '0')

/** 列表统一格式：YYYY-MM-DD HH:mm */
export function fmtTime(s) {
  const d = parse(s)
  if (!d) return s || ''
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / 昨天 HH:mm / M月D日 / YYYY年M月D日（通知类场景） */
export function fmtRelative(s) {
  const d = parse(s)
  if (!d) return s || ''
  const diff = Date.now() - d.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
  const now = new Date()
  const yest = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  if (d >= yest) return `昨天 ${p2(d.getHours())}:${p2(d.getMinutes())}`
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日`
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}
