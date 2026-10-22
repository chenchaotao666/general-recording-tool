import { formatCurrency, formatDate, formatNumber } from './format.js'

export const CLIPBOARD_TYPE = 'application/x-smart-table-cells'
export const READONLY_MESSAGE = '此列类型由系统自动生成，不支持手动修改。'
export const TYPE_MESSAGE = '粘贴内容与类型不符，请修改列类型后再试。'
const enums = ['singleSelect', 'multiSelect']
const numbers = ['number', 'currency', 'percent', 'progress']
const readonly = ['formula', 'lookup', 'autoNumber', 'serial', 'createdBy', 'createdTime', 'lastModifiedBy', 'lastModifiedTime']
export const cellType = f => f.field_type === 'ai' ? f.options?.outputType || 'text' : f.field_type
export const isGenerated = f => readonly.includes(f.field_type) || !!f.options?.formula || !!f.options?.serial || f.data_type === 'serial'
const list = v => v == null || v === '' ? [] : Array.isArray(v) ? v : [v]

// Serialize the entire value, independently of clipping, +N badges and mounted rows.
export function displayCell(field, value, dirs = {}) {
  if (value == null) return ''
  const type = cellType(field), cfg = field.options || {}
  if (enums.includes(type)) return list(value).map(v => cfg.options?.find(o => String(o.id) === String(v))?.label ?? String(v)).join('、')
  if (['member', 'createdBy', 'lastModifiedBy'].includes(type)) return list(value).map(v => ({ __ai__: 'AI 生成', __automation__: '自动化' })[v] || dirs.members?.get(Number(v))?.name || '未知成员').join('、')
  if (type === 'relation') return list(value).map(v => dirs.relations?.get(cfg.targetTableId)?.get(Number(v)) || '未命名记录').join('、')
  if (type === 'url') return value.text || value.url || String(value)
  if (['file', 'image'].includes(type)) return list(value).map(v => v.name || v.filename || (type === 'image' ? '图片' : '文件')).join('、')
  if (type === 'lookup' && field.lookupDisplayField) {
    const source = field.lookupDisplayField
    if (!['raw', 'rawDistinct'].includes(cfg.aggregation || 'raw')) return formatNumber(value, {})
    return list(value).map(v => displayCell(source, v, dirs)).join('、')
  }
  if (['date', 'createdTime', 'lastModifiedTime'].includes(type)) return formatDate(value, cfg)
  if (type === 'number') return formatNumber(value, cfg)
  if (type === 'currency') return formatCurrency(value, cfg)
  if (type === 'percent') return value === '' ? '' : `${value}%`
  if (type === 'progress') {
    const percent = cfg.numberFormat === 'percent'
    const min = Number(cfg.min ?? 0), max = Number(cfg.max ?? 100)
    const n = percent ? (Number(value) - min) / (max - min) * 100 : Number(value)
    return (cfg.precision == null || cfg.precision === 'default' ? String(+n.toFixed(4)) : n.toFixed(Number(cfg.precision))) + (percent ? '%' : '')
  }
  if (type === 'checkbox') return value ? '是' : '否'
  return typeof value === 'object' ? list(value).map(v => v?.label || v?.name || v?.text || '').join('、') : String(value)
}

export function copyCell(field, value, dirs) {
  const text = displayCell(field, value, dirs)
  return { type: cellType(field), value, text, targetTableId: field.options?.targetTableId,
    labels: enums.includes(cellType(field)) ? list(value).map(v => field.options?.options?.find(o => String(o.id) === String(v))?.label ?? String(v)) : undefined }
}
export function toTSV(matrix) {
  return matrix.map(row => row.map(cell => {
    const text = typeof cell === 'string' ? cell : cell.text
    return /[\t\r\n"]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
  }).join('\t')).join('\n')
}
export function fromTSV(text) {
  const rows = [[]]; let value = '', quoted = false
  text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '"' && (quoted || !value)) {
      if (quoted && text[i + 1] === '"') { value += '"'; i++ } else quoted = !quoted
    } else if (!quoted && (c === '\t' || c === '\n')) {
      rows.at(-1).push(value); value = ''
      if (c === '\n') rows.push([])
    } else value += c
  }
  rows.at(-1).push(value)
  if (text.endsWith('\n') && rows.at(-1).length === 1 && !rows.at(-1)[0]) rows.pop()
  const width = Math.max(...rows.map(r => r.length))
  return rows.map(row => Array.from({ length: width }, (_, i) => ({ type: 'text', text: row[i] || '', value: row[i] || '' })))
}
export function readClipboard(data) {
  const plain = data.getData('text/plain')
  try {
    const payload = JSON.parse(data.getData(CLIPBOARD_TYPE))
    if (payload.version === 1 && Array.isArray(payload.cells) && payload.cells.length &&
        payload.cells.every(r => Array.isArray(r) && r.length === payload.cells[0].length && r.every(c => typeof c?.text === 'string')) && toTSV(payload.cells) === plain) return payload.cells
  } catch { /* External clipboard: read ordinary TSV. */ }
  return fromTSV(plain)
}
export function convertCell(source, field) {
  if (isGenerated(field)) throw new Error(READONLY_MESSAGE)
  const type = cellType(field), cfg = field.options || {}, text = source.text
  if (type === 'text') return { value: text }
  if (!text && (source.value == null || source.value === '' || Array.isArray(source.value) && !source.value.length)) return { value: null }
  if (enums.includes(type) && (source.type === 'text' || enums.includes(source.type))) {
    const labels = source.labels || (type === 'singleSelect' ? [text] : text.split(/[、,，;；\n]/).map(s => s.trim()).filter(Boolean))
    if (cfg.optionSource === 'reference') {
      const ids = labels.map(label => cfg.options?.find(o => o.label === label)?.id)
      if (ids.some(id => id == null)) throw new Error('引用选项列不能新增选项，请先在来源列中添加。')
      return { value: type === 'singleSelect' ? ids[0] ?? null : ids }
    }
    return { labels: [...new Set(labels)] }
  }
  if (numbers.includes(type) && (numbers.includes(source.type) || source.type === 'text')) {
    const raw = source.type === 'text' ? text.trim().replace(/%$/, '') : source.value
    if (source.type === 'text' && !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)) throw new Error(TYPE_MESSAGE)
    let value = Number(raw)
    if (!Number.isFinite(value)) throw new Error(TYPE_MESSAGE)
    if (type === 'progress') {
      const min = Number(cfg.min ?? 0), max = Number(cfg.max ?? 100)
      if (source.type === 'text' && text.trim().endsWith('%')) value = min + value / 100 * (max - min)
      if (value < min || value > max) throw new Error(TYPE_MESSAGE)
    }
    return { value }
  }
  if (type === 'checkbox' && (source.type === 'checkbox' || source.type === 'text')) {
    if (/^(true|1|是|✓)$/i.test(text)) return { value: true }
    if (/^(false|0|否)$/i.test(text)) return { value: false }
  }
  if (type === 'date' && (source.type === 'date' || source.type === 'text')) {
    const value = source.type === 'date' ? source.value : text.trim()
    if (/^\d{4}-\d{2}-\d{2}(?:[ T].*)?$/.test(value) && !Number.isNaN(Date.parse(value)) &&
        new Date(value.slice(0, 10)).toISOString().slice(0, 10) === value.slice(0, 10)) return { value }
  }
  if (type === 'url' && source.type === 'text' && /^https?:\/\/\S+$/i.test(text)) return { value: { text, url: text } }
  if (type === source.type && ['url', 'member', 'file', 'image', 'relation'].includes(type)) {
    if (type === 'relation' && Number(cfg.targetTableId) !== Number(source.targetTableId)) throw new Error(TYPE_MESSAGE)
    return { value: source.value }
  }
  throw new Error(TYPE_MESSAGE)
}

export function rangeBounds(rows, fields, anchor, end = anchor) {
  if (!anchor || !end) return null
  const r1 = rows.findIndex(r => r.__key === anchor.key), r2 = rows.findIndex(r => r.__key === end.key)
  const c1 = fields.findIndex(f => f.field_name === anchor.fieldName), c2 = fields.findIndex(f => f.field_name === end.fieldName)
  if (Math.min(r1, r2, c1, c2) < 0) return null
  return { top: Math.min(r1, r2), bottom: Math.max(r1, r2), left: Math.min(c1, c2), right: Math.max(c1, c2) }
}
export function planPaste(matrix, rows, fields, bounds, canEdit = () => true) {
  const h = matrix.length, w = matrix[0]?.length
  if (!h || !w || !bounds) return { changes: [], skipped: [] }
  const height = bounds.bottom - bounds.top + 1, width = bounds.right - bounds.left + 1
  const repeat = height >= h && width >= w && height % h === 0 && width % w === 0
  const nr = repeat ? height : h, nc = repeat ? width : w
  const changes = [], skipped = []
  // Keep source coordinates unchanged when an individual destination is skipped.
  for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
    const row = rows[bounds.top + r], field = fields[bounds.left + c]
    try {
      if (!row || !field) throw new Error('粘贴范围超出当前表格。')
      if (isGenerated(field)) throw new Error(READONLY_MESSAGE)
      if (!canEdit(row, field)) throw new Error('你没有编辑该单元格的权限')
      changes.push({ row, field, ...convertCell(matrix[r % h][c % w], field) })
    } catch (error) { skipped.push({ row, field, reason: error.message }) }
  }
  return { changes, skipped }
}
