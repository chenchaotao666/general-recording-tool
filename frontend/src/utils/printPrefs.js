// 打印相关偏好（localStorage）：纸张、每表上次使用的模板、设计器占位符面板折叠态。
// 所有读写都包 try/catch——隐私模式/禁用存储时静默降级为默认值。

const KEY_PAPER = 'grt.print.paper'
const PAPERS = ['a4', 'half', 'third']

export function getPaper() {
  try {
    const p = localStorage.getItem(KEY_PAPER)
    return PAPERS.includes(p) ? p : 'a4'
  } catch { return 'a4' }
}

export function setPaper(p) {
  try { localStorage.setItem(KEY_PAPER, p) } catch { /* 忽略 */ }
}

const keyLastTpl = (tableId) => `grt.print.lastTpl.${tableId}`

export function getLastTpl(tableId) {
  try {
    return Number(localStorage.getItem(keyLastTpl(tableId))) || null
  } catch { return null }
}

export function setLastTpl(tableId, id) {
  try { localStorage.setItem(keyLastTpl(tableId), String(id)) } catch { /* 忽略 */ }
}

const KEY_CFG_COLLAPSED = 'grt.printDesigner.cfgCollapsed'

export function getCfgCollapsed() {
  try { return localStorage.getItem(KEY_CFG_COLLAPSED) === '1' } catch { return false }
}

export function setCfgCollapsed(v) {
  try { localStorage.setItem(KEY_CFG_COLLAPSED, v ? '1' : '0') } catch { /* 忽略 */ }
}
