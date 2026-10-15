// 智能表字段类型注册表（设计文档 §3.4）：前端单一事实来源
// 每类型注册：图标/名称/分组/默认配置/运算符/编辑器/渲染器形态/聚合能力

export const OPTION_COLORS = [
  { key: 'blue', label: '蓝', value: '#e8f0fe', text: '#1967d2' },
  { key: 'cyan', label: '青', value: '#e0f7fa', text: '#00838f' },
  { key: 'green', label: '绿', value: '#e6f4ea', text: '#188038' },
  { key: 'orange', label: '橙', value: '#feefe3', text: '#e8710a' },
  { key: 'red', label: '红', value: '#fce8e6', text: '#d93025' },
  { key: 'purple', label: '紫', value: '#f3e8fd', text: '#9334e6' },
  { key: 'pink', label: '粉', value: '#fce4ec', text: '#d81b60' },
  { key: 'yellow', label: '黄', value: '#fef9e0', text: '#b06000' },
  { key: 'gray', label: '灰', value: '#f1f3f4', text: '#5f6368' },
]

// 填色色板（设计稿 PixPin_2026-10-15_20-26-47）：9 色 × 3 深浅档，按行浅→深
export const FILL_PALETTE = [
  ['#f1f3f4', '#e8f0fe', '#e0f7fa', '#e6f4ea', '#fce8e6', '#feefe3', '#fef9e0', '#f3e8fd', '#fce4ec'],
  ['#dadce0', '#aecbfa', '#9ee7f0', '#a9e5c0', '#f6b8b3', '#fbcfa6', '#fde293', '#d0aff2', '#f8a8cd'],
  ['#bdc1c6', '#8ab4f8', '#5fd4e0', '#81c995', '#ee675c', '#f2995c', '#fcc934', '#b475e8', '#f06292'],
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

const OP_TEXT = ['contains', 'notContains', 'eq', 'neq', 'isEmpty', 'isNotEmpty']
const OP_NUMBER = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'isEmpty', 'isNotEmpty']
const OP_ENUM = ['contains', 'notContains', 'eq', 'neq', 'isEmpty', 'isNotEmpty']
const OP_DATE = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'today', 'pastDays', 'withinDays', 'isEmpty', 'isNotEmpty']

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
  phone: { label: '电话', icon: '📞', group: '标识', editor: 'inline', filterOps: OP_TEXT, aggregations: ['count'], defaultConfig: () => ({}) },
  email: { label: '邮箱', icon: '✉', group: '标识', editor: 'inline', filterOps: OP_TEXT, aggregations: ['count'], defaultConfig: () => ({}) },
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
  lastModifiedTime: { label: '最后编辑时间', icon: '📅', group: '系统', editor: 'readonly', filterOps: OP_DATE, aggregations: ['count'], readonly: true, system: true, defaultConfig: () => ({ format: 'yyyy-MM-dd' }) },
}

export const FIELD_TYPE_GROUPS = ['基础', '协作', '媒体', '标识', '关联', '计算', '系统']

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
