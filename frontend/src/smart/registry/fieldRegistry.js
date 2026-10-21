// 智能表字段类型注册表（设计文档 §3.4）：前端单一事实来源
// 每类型注册：图标/名称/分组/默认配置/运算符/编辑器/渲染器形态/聚合能力

export const OPTION_COLORS = [
  { key: 'blue', label: '蓝', value: '#D9E7FF', text: '#2460C9' },
  { key: 'cyan', label: '青', value: '#D5F4F4', text: '#0E7C86' },
  { key: 'green', label: '绿', value: '#D8F5DF', text: '#1E7E34' },
  { key: 'orange', label: '橙', value: '#FFE8CC', text: '#B25009' },
  { key: 'red', label: '红', value: '#FDE3E3', text: '#C92A2A' },
  { key: 'purple', label: '紫', value: '#F0E4F7', text: '#7E3FBF' },
  { key: 'pink', label: '粉', value: '#FDE8EF', text: '#C22A66' },
  { key: 'yellow', label: '黄', value: '#FDF3D7', text: '#8A6D1A' },
  { key: 'gray', label: '灰', value: '#F0F1F3', text: '#646A73' },
]

// css 仅用于色板图标；单元格按进度比例从 colors 中取一种颜色。
export const PROGRESS_COLORS = [
  { key: 'blue', css: '#4E8CF7' }, { key: 'cyan', css: '#5DD3C9' }, { key: 'green', css: '#3DC15E' },
  { key: 'red', css: '#F5554A' }, { key: 'orange', css: '#FA7D2E' }, { key: 'yellow', css: '#FCB900' },
  { key: 'purple', css: '#8B5CF6' }, { key: 'pink', css: '#F2699A' }, { key: 'gray', css: '#B6B8BC' },
  { key: 'g-blue', css: 'linear-gradient(90deg, #DCE8FD, #4E8CF7)' },
  { key: 'g-cyan', css: 'linear-gradient(90deg, #E0F7F4, #5DD3C9)' },
  { key: 's-green-red', css: 'linear-gradient(90deg, #3DC15E 50%, #F5554A 50%)' },
  { key: 's-red-green', css: 'linear-gradient(90deg, #F5554A 50%, #3DC15E 50%)' },
  { key: 's-blue-orange', css: 'linear-gradient(90deg, #4E8CF7 50%, #FA7D2E 50%)' },
  { key: 's-orange-blue', css: 'linear-gradient(90deg, #FA7D2E 50%, #4E8CF7 50%)' },
  { key: 's-ryg', css: 'linear-gradient(90deg, #F5554A 33%, #FCB900 33% 66%, #3DC15E 66%)' },
  { key: 's-gyr', css: 'linear-gradient(90deg, #3DC15E 33%, #FCB900 33% 66%, #F5554A 66%)' },
  { key: 's-rainbow', css: 'linear-gradient(90deg, #F5554A 16.67%, #FA7D2E 16.67% 33.33%, #FCB900 33.33% 50%, #3DC15E 50% 66.67%, #4E8CF7 66.67% 83.33%, #8B5CF6 83.33%)' },
]
const PROGRESS_SCHEMES = {
  'g-blue': ['浅蓝到深蓝', ['#DCE8FD', '#4E8CF7']],
  'g-cyan': ['浅青到深青', ['#E0F7F4', '#5DD3C9']],
  's-green-red': ['绿 → 红', ['#3DC15E', '#F5554A']],
  's-red-green': ['红 → 绿', ['#F5554A', '#3DC15E']],
  's-blue-orange': ['蓝 → 橙', ['#4E8CF7', '#FA7D2E']],
  's-orange-blue': ['橙 → 蓝', ['#FA7D2E', '#4E8CF7']],
  's-ryg': ['红 → 黄 → 绿', ['#F5554A', '#FCB900', '#3DC15E']],
  's-gyr': ['绿 → 黄 → 红', ['#3DC15E', '#FCB900', '#F5554A']],
  's-rainbow': ['彩虹', ['#F5554A', '#FA7D2E', '#FCB900', '#3DC15E', '#4E8CF7', '#8B5CF6']],
}
PROGRESS_COLORS.forEach(c => { c.label = PROGRESS_SCHEMES[c.key]?.[0] || OPTION_COLORS.find(o => o.key === c.key)?.label || c.key })
export function progressColor(key, ratio = 0) {
  const colors = PROGRESS_SCHEMES[key]?.[1]
  if (!colors) return PROGRESS_COLORS.find(c => c.key === key)?.css || key || '#3DC15E'
  const p = Math.min(1, Math.max(0, Number(ratio) || 0))
  if (key.startsWith('g-')) {
    const channels = [1, 3, 5].map(i => Math.round(parseInt(colors[0].slice(i, i + 2), 16) * (1 - p)
      + parseInt(colors[1].slice(i, i + 2), 16) * p).toString(16).padStart(2, '0'))
    return `#${channels.join('')}`
  }
  return colors[Math.min(colors.length - 1, Math.floor(p * colors.length))]
}

// 填色色板（设计稿 PixPin_2026-10-15_20-26-47）：9 色 × 3 深浅档，按行浅→深
export const FILL_PALETTE = [
  ['#F2F3F5', '#DFE9FC', '#DFF2FB', '#DFF6F3', '#FDE4E4', '#FDEEE4', '#FEF5DA', '#ECE8FC', '#FCE6EF'],
  ['#E3E4E6', '#ABC8F7', '#B3E0F7', '#B5E8E1', '#FBC2C0', '#FCCEB0', '#FDE5A6', '#CFC4F7', '#F7C3D9'],
  ['#D5D6D8', '#82B1F5', '#8DCDF2', '#8DDBD1', '#F79E9B', '#FAB287', '#FCD574', '#AD98F1', '#F29DBF'],
]

export function optionColor(key) {
  return OPTION_COLORS.find(c => c.key === key) || OPTION_COLORS[0]
}

export const OP_LABELS = {
  contains: '包含', notContains: '不包含', eq: '等于', neq: '不等于',
  gt: '大于', gte: '大于等于', lt: '小于', lte: '小于等于',
  isEmpty: '为空', isNotEmpty: '不为空',
  today: '今天', pastDays: '过去 N 天', withinDays: '未来 N 天',
}
export const NO_VALUE_OPS = ['isEmpty', 'isNotEmpty', 'today']

// 日期字段的比较运算符文案：大于/小于 → 晚于/早于（参照 PixPin_2026-10-18_00-48-13）
const DATE_OP_LABELS = { gt: '晚于', lt: '早于', gte: '不早于', lte: '不晚于' }
const DATE_TYPES = ['date', 'createdTime', 'lastModifiedTime']
export function opLabel(field, op) {
  if (DATE_TYPES.includes(field?.field_type) && DATE_OP_LABELS[op]) return DATE_OP_LABELS[op]
  return OP_LABELS[op] || op || ''
}

const OP_TEXT = ['contains', 'notContains', 'eq', 'neq', 'isEmpty', 'isNotEmpty']
const OP_NUMBER = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'isEmpty', 'isNotEmpty']
const OP_ENUM = ['contains', 'notContains', 'eq', 'neq', 'isEmpty', 'isNotEmpty']
// 日期：等于 / 不等于 / 晚于 / 早于 / 为空 / 不为空；今天、本周、过去 7 天等相对日期改由值的「日期模式」表达。
// 旧条件里的 gte/lte/today/pastDays/withinDays 后端仍可求值，文案照常显示，只是不再出现在可选列表
const OP_DATE = ['eq', 'neq', 'gt', 'lt', 'isEmpty', 'isNotEmpty']

// editor: inline（内联输入）/ select / date / member / url / progress / upload / relation / checkbox(即时) / readonly
export const FIELD_REGISTRY = {
  text: { label: '文本', icon: 'A', group: '基础', editor: 'inline', filterOps: OP_TEXT, aggregations: ['count'], defaultConfig: () => ({}) },
  singleSelect: { label: '单选', icon: '⊙', group: '基础', editor: 'select', filterOps: OP_ENUM, aggregations: ['count'], defaultConfig: () => ({ options: [], allowAddOptionWhenEditing: true }) },
  multiSelect: { label: '多选', icon: '☰', group: '基础', editor: 'select', filterOps: OP_ENUM, aggregations: ['count'], defaultConfig: () => ({ options: [], allowAddOptionWhenEditing: true }), multiple: true },
  number: { label: '数字', icon: '₁₂₃', group: '基础', editor: 'inline', filterOps: OP_NUMBER, aggregations: ['count', 'sum', 'avg', 'max', 'min'], defaultConfig: () => ({ precision: 'default', thousandSeparator: false }) },
  percent: { label: '百分数', icon: '%', group: '基础', editor: 'inline', suffix: '%', filterOps: OP_NUMBER, aggregations: ['count', 'sum', 'avg', 'max', 'min'], defaultConfig: () => ({ precision: 'default', thousandSeparator: false }) },
  currency: { label: '货币', icon: '¥', group: '基础', editor: 'inline', filterOps: OP_NUMBER, aggregations: ['count', 'sum', 'avg', 'max', 'min'], defaultConfig: () => ({ currencyCode: 'CNY', currencySymbol: '￥', precision: 2, thousandSeparator: true }) },
  date: { label: '日期', icon: '📅', group: '基础', editor: 'date', filterOps: OP_DATE, aggregations: ['count', 'max', 'min'], defaultConfig: () => ({ format: 'yyyy-MM-dd', includeTime: false, autoFillCreatedTime: false }) },
  checkbox: { label: '复选框', icon: '☑', group: '基础', editor: 'checkbox', filterOps: ['eq', 'isEmpty', 'isNotEmpty'], aggregations: ['count'], defaultConfig: () => ({ defaultChecked: false }) },
  url: { label: '链接', icon: '🔗', group: '标识', editor: 'url', filterOps: OP_TEXT, aggregations: ['count'], defaultConfig: () => ({ displayStyle: 'iconText' }) },
  member: { label: '人员', icon: '👤', group: '协作', editor: 'member', filterOps: OP_ENUM, aggregations: ['count'], defaultConfig: () => ({ multiple: true, notifyOnAdd: true }) },
  // V2
  progress: { label: '进度', icon: '▱', group: '基础', editor: 'progress', filterOps: OP_NUMBER, aggregations: ['count', 'sum', 'avg', 'max', 'min'], defaultConfig: () => ({ color: 'green', numberFormat: 'value', range: { min: 0, max: 100 }, showNumber: true }) },
  image: { label: '图片', icon: '🖼', group: '媒体', editor: 'upload', filterOps: ['isEmpty', 'isNotEmpty'], aggregations: ['count'], defaultConfig: () => ({ cameraOnly: false }) },
  file: { label: '文件', icon: '📁', group: '媒体', editor: 'upload', filterOps: ['isEmpty', 'isNotEmpty'], aggregations: ['count'], defaultConfig: () => ({}) },
  autoNumber: { label: '自动编号', icon: '1⇓', group: '标识', editor: 'readonly', filterOps: OP_TEXT, aggregations: ['count'], defaultConfig: () => ({ numberType: 'autoIncrement', segments: [{ type: 'autoIncrement', digits: 3 }] }), readonly: true },
  relation: { label: '关联', icon: '🔗⇢', group: '关联', editor: 'relation', filterOps: OP_ENUM, aggregations: ['count'], defaultConfig: () => ({ targetTableId: null, multiple: true, bidirectional: false }) },
  lookup: { label: '查找引用', icon: '🧾', group: '关联', editor: 'readonly', filterOps: ['isEmpty', 'isNotEmpty'], aggregations: ['count'], readonly: true, computed: true, defaultConfig: () => ({ sourceTableId: null, sourceFieldId: null, conditionLogic: 'and', conditions: [], aggregation: 'raw' }) },
  formula: { label: '公式', icon: 'fx', group: '计算', editor: 'readonly', filterOps: OP_TEXT, aggregations: ['count'], readonly: true, defaultConfig: () => ({ formula: '', returnType: 'text' }) },
  createdBy: { label: '创建人', icon: '👤', group: '系统', editor: 'readonly', filterOps: OP_ENUM, aggregations: ['count'], readonly: true, system: true, defaultConfig: () => ({}) },
  lastModifiedBy: { label: '最后编辑人', icon: '👤', group: '系统', editor: 'readonly', filterOps: OP_ENUM, aggregations: ['count'], readonly: true, system: true, defaultConfig: () => ({}) },
  createdTime: { label: '创建时间', icon: '📅', group: '系统', editor: 'readonly', filterOps: OP_DATE, aggregations: ['count'], readonly: true, system: true, defaultConfig: () => ({ format: 'yyyy-MM-dd' }) },
  // V3：AI 字段（场景市场配置；值由服务端 AI 回写，按 outputType 渲染）
  ai: { label: 'AI 字段', icon: '✦', group: '计算', editor: 'readonly', filterOps: OP_TEXT, aggregations: ['count'], readonly: true, ai: true, defaultConfig: () => ({ scene: 'custom', inputFields: [], prompt: '', outputType: 'text', options: [], autoUpdate: true, allowNewOptions: true }) },
  lastModifiedTime: { label: '最后编辑时间', icon: '📅', group: '系统', editor: 'readonly', filterOps: OP_DATE, aggregations: ['count'], readonly: true, system: true, defaultConfig: () => ({ format: 'yyyy-MM-dd' }) },
}

export const FIELD_TYPE_GROUPS = ['基础', '协作', '媒体', '标识', '关联', '计算', '系统']

// 不可直接编辑的字段：单击/双击时的提示文案（表格单元格与右侧详情面板共用）；
// BLOCKED_CONFIGURABLE 可通过提示里的「修改设置」调整规则
export const BLOCKED_EDIT_TEXT = {
  formula: '公式计算结果不可直接编辑', lookup: '查找引用内容不可直接编辑', autoNumber: '自动编号不可直接编辑',
  createdBy: '创建人由系统自动记录，不可直接编辑', lastModifiedBy: '最后编辑人由系统自动记录，不可直接编辑',
  createdTime: '创建时间由系统自动记录，不可直接编辑', lastModifiedTime: '最后编辑时间由系统自动记录，不可直接编辑',
}
export const BLOCKED_CONFIGURABLE = ['formula', 'lookup', 'autoNumber', 'createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime']

export function regOf(field) {
  return FIELD_REGISTRY[field?.field_type] || FIELD_REGISTRY.text
}

export function filterOpsOf(field) {
  return regOf(field).filterOps
}

// 排序方向文案（设计文档 §5.3：类型自适应）
export function sortDirectionLabels(field) {
  const ft = field?.field_type
  if (ft === 'singleSelect' || ft === 'multiSelect') return ['选项正序', '选项逆序']
  if (['number', 'percent', 'currency', 'progress'].includes(ft)) return ['0 → 9', '9 → 0']
  if (['date', 'createdTime', 'lastModifiedTime'].includes(ft)) return ['早 → 晚', '晚 → 早']
  return ['A → Z', 'Z → A']
}

// 视图筛选 DSL → 后端运算符映射与 dyn filters 适配
const OP_MAP = {
  contains: 'contains', notContains: 'not_contains', eq: 'eq', neq: 'ne',
  gt: 'gt', gte: 'gte', lt: 'lt', lte: 'lte', isEmpty: 'empty', isNotEmpty: 'not_empty',
  today: 'today', pastDays: 'past_days', withinDays: 'within_days',
}
export function conditionToRule(c) {
  const op = OP_MAP[c.operator]
  if (!op) return null
  const rule = { field: c.fieldId, op }
  if (!NO_VALUE_OPS.includes(c.operator)) rule.value = c.value
  return rule
}

// ---------- 统计行（footer）按列统计方式 ----------
export const STAT_LABELS = {
  sum: '求和', avg: '平均值', max: '最大值', min: '最小值',
  countRecords: '记录行数', empty: '未填写', count: '已填写', distinct: '去重计数',
  emptyRatio: '未填写占比', filledRatio: '已填写占比', distinctRatio: '去重占比',
}
// 通用统计（所有字段类型可选，与后端 view_config.GENERIC_AGGS 对齐）
export const GENERIC_STATS = ['countRecords', 'empty', 'count', 'distinct', 'emptyRatio', 'filledRatio', 'distinctRatio']

// 某字段统计行可选的统计方式：注册表数值聚合（sum/avg/max/min）在前，通用统计在后
export function footerStatsOf(field) {
  const extras = (regOf(field).aggregations || []).filter(a => a !== 'count')
  return [...extras, ...GENERIC_STATS]
}

// 统计值展示格式化：占比（后端返回 0~1 小数）→ 百分比；非整数保留两位；
// 日期类字段的最值按 includeTime 选项裁掉时间部分
export function formatStatValue(agg, v, field) {
  if (v == null) return ''
  if (agg.endsWith('Ratio')) return `${(v * 100).toFixed(2)}%`
  if (typeof v === 'string' && ['date', 'createdTime', 'lastModifiedTime'].includes(field?.field_type)
      && !field?.options?.includeTime && /^\d{4}-\d{2}-\d{2}/.test(v)) {
    return v.slice(0, 10)
  }
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(2)
  return String(v)
}
