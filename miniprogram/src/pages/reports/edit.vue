<template>
  <view class="page">
    <!-- AI 辅助 -->
    <view class="ai-box">
      <textarea v-model="aiDesc" class="ai-textarea" placeholder="AI 辅助：用自然语言描述报表，自动生成时间口径和区块" />
      <view class="ai-btn" @click="aiGenerate">{{ aiGenerating ? 'AI 设计中…' : '✨ AI 生成' }}</view>
      <view v-if="aiNotes" class="ai-notes">{{ aiNotes }}</view>
    </view>

    <view class="form-item">
      <view class="label">报表名称 <text class="required">*</text></view>
      <input v-model="form.name" class="input" placeholder="如：客户跟进周报" />
    </view>

    <view class="form-item">
      <view class="label">数据表 <text class="required">*</text></view>
      <picker :range="tables" range-key="label" :value="tableIndex" @change="onTableChange">
        <view class="picker-value" :class="{ placeholder: tableIndex < 0 }">
          {{ tableIndex >= 0 ? tables[tableIndex].label : '请选择数据表' }}
        </view>
      </picker>
    </view>

    <view class="form-item">
      <view class="label">时间口径 <text class="required">*</text></view>
      <view class="radio-row" style="margin-bottom: 16rpx">
        <view v-for="[v, l] in RANGE_MODES" :key="v" class="radio sm" :class="{ active: form.range.mode === v }" @click="form.range.mode = v">{{ l }}</view>
      </view>
      <view class="fc-row">
        <text class="lbl">统计字段</text>
        <picker :range="dateFieldOptions" range-key="label" @change="(e) => (form.range.date_field = dateFieldOptions[Number(e.detail.value)].value)">
          <view class="fc-picker wide">{{ dateFieldLabel }} ›</view>
        </picker>
      </view>
      <view v-if="form.range.mode === 'custom'" class="fc-row">
        <picker mode="date" :value="form.range.start || ''" @change="(e) => (form.range.start = e.detail.value)">
          <view class="fc-picker wide">{{ form.range.start || '开始日期' }} ›</view>
        </picker>
        <picker mode="date" :value="form.range.end || ''" @change="(e) => (form.range.end = e.detail.value)">
          <view class="fc-picker wide">{{ form.range.end || '结束日期' }} ›</view>
        </picker>
      </view>
    </view>

    <!-- 区块列表 -->
    <view class="sec-title">报表区块（{{ form.blocks.length }}）· 筛选在时间范围上叠加</view>
    <view v-for="(b, i) in form.blocks" :key="b.id" class="block-card">
      <view class="bc-head">
        <text class="bc-tag" :class="'tag-' + b.type">{{ BLOCK_LABELS[b.type] }}</text>
        <input v-model="b.title" class="bc-title" placeholder="区块标题" />
        <text class="bc-op" :class="{ dim: i === 0 }" @click="moveBlock(i, -1)">↑</text>
        <text class="bc-op" :class="{ dim: i === form.blocks.length - 1 }" @click="moveBlock(i, 1)">↓</text>
        <text class="bc-op del" @click="form.blocks.splice(i, 1)">删</text>
      </view>

      <!-- 统计卡片 -->
      <view v-if="b.type === 'stat'" class="fc-row">
        <picker :range="STAT_AGGS" range-key="label" @change="(e) => onAggChange(b, STAT_AGGS[Number(e.detail.value)].value)">
          <view class="fc-picker">{{ aggLabel(b.agg) }} ›</view>
        </picker>
        <picker v-if="needsField(b.agg)" :range="aggFields(b.agg)" range-key="label" @change="(e) => (b.field = aggFields(b.agg)[Number(e.detail.value)].field_name)">
          <view class="fc-picker wide">{{ fieldLabel(b.field) || (b.agg === 'count_distinct' ? '统计字段' : '数值字段') }} ›</view>
        </picker>
        <text class="chip" :class="{ on: b.compare }" @click="b.compare = !b.compare">环比上期</text>
      </view>

      <!-- 图表 -->
      <template v-else-if="b.type === 'chart'">
        <view class="radio-row" style="margin-bottom: 12rpx">
          <view v-for="[v, l] in CHART_TYPES" :key="v" class="radio sm" :class="{ active: b.chart_type === v }" @click="b.chart_type = v">{{ l }}</view>
        </view>
        <view class="fc-row">
          <picker :range="GROUP_KINDS" range-key="label" @change="(e) => onGroupKind(b, e)">
            <view class="fc-picker">{{ GROUP_KINDS.find((g) => g.value === b.group.kind)?.label }} ›</view>
          </picker>
          <picker :range="groupFields(b.group.kind)" range-key="label" @change="(e) => (b.group.field = groupFields(b.group.kind)[Number(e.detail.value)].field_name)">
            <view class="fc-picker wide">{{ fieldLabel(b.group.field) || '分组字段' }} ›</view>
          </picker>
        </view>
        <view class="fc-row">
          <picker :range="CHART_AGGS" range-key="label" @change="(e) => onAggChange(b, CHART_AGGS[Number(e.detail.value)].value)">
            <view class="fc-picker">{{ aggLabel(b.agg) }} ›</view>
          </picker>
          <picker v-if="needsField(b.agg)" :range="aggFields(b.agg)" range-key="label" @change="(e) => (b.field = aggFields(b.agg)[Number(e.detail.value)].field_name)">
            <view class="fc-picker wide">{{ fieldLabel(b.field) || (b.agg === 'count_distinct' ? '统计字段' : '数值字段') }} ›</view>
          </picker>
          <template v-if="b.chart_type === 'pie'">
            <text class="lbl-sm">前N项</text>
            <input v-model="b.top_n" type="number" class="fc-input" style="max-width: 120rpx" />
          </template>
        </view>
      </template>

      <!-- 明细表 -->
      <template v-else-if="b.type === 'table'">
        <view class="lbl-sm" style="margin-bottom: 8rpx">列（点击切换）</view>
        <view class="chip-row" style="margin-bottom: 12rpx">
          <text
            v-for="c in allColumns" :key="c.value"
            class="chip" :class="{ on: b.columns.includes(c.value) }"
            @click="toggleColumn(b, c.value)"
          >{{ c.label }}</text>
        </view>
        <view class="fc-row">
          <text class="lbl-sm">排序</text>
          <picker :range="allColumns" range-key="label" @change="(e) => (b.sort_by = allColumns[Number(e.detail.value)].value)">
            <view class="fc-picker wide">{{ columnLabel(b.sort_by) }} ›</view>
          </picker>
          <picker :range="['降序', '升序']" @change="(e) => (b.sort_order = Number(e.detail.value) === 0 ? 'desc' : 'asc')">
            <view class="fc-picker">{{ b.sort_order === 'asc' ? '升序' : '降序' }} ›</view>
          </picker>
          <text class="lbl-sm">上限</text>
          <input v-model="b.limit" type="number" class="fc-input" style="max-width: 120rpx" />
        </view>
      </template>

      <!-- 文本 -->
      <template v-else-if="b.type === 'text'">
        <textarea v-model="b.content" class="textarea" placeholder="支持 {range_label} 和 {b1} 引用统计卡片的值" />
        <view class="chip-row">
          <text v-for="s in statBlocks" :key="s.id" class="chip" @click="b.content += `{${s.id}}`">{{ s.title || s.id }}</text>
        </view>
      </template>

      <!-- 筛选 -->
      <view v-if="b.type !== 'text'" class="bc-filters">
        <view class="lbl-sm" style="margin-bottom: 8rpx">筛选（可选）</view>
        <view v-for="(r, ri) in b.filters.rules" :key="ri" class="fc-row">
          <picker :range="fieldOptions" range-key="label" @change="(e) => { r.field = fieldOptions[Number(e.detail.value)].field_name; r.value = null }">
            <view class="fc-picker wide">{{ fieldLabel(r.field) || '字段' }} ›</view>
          </picker>
          <picker :range="opsFor(r.field)" range-key="label" @change="(e) => (r.op = opsFor(r.field)[Number(e.detail.value)].value)">
            <view class="fc-picker">{{ opLabel(r) }} ›</view>
          </picker>
          <text class="bc-op del" @click="b.filters.rules.splice(ri, 1)">删</text>
        </view>
        <template v-for="(r, ri) in b.filters.rules" :key="'v' + ri">
          <view v-if="!NO_VALUE_OPS.includes(r.op)" class="fc-row">
            <input
              v-if="DAY_OPS.includes(r.op)" v-model="r.value" type="number" class="fc-input" placeholder="天数"
            />
            <picker
              v-else-if="fieldOf(r.field)?.widget === 'select'"
              :range="selectOptions(fieldOf(r.field))"
              @change="(e) => (r.value = selectOptions(fieldOf(r.field))[Number(e.detail.value)])"
            >
              <view class="fc-picker wide">{{ r.value || '选择值' }} ›</view>
            </picker>
            <picker
              v-else-if="['date', 'datetime'].includes(fieldOf(r.field)?.data_type)" mode="date"
              :value="r.value || ''" @change="(e) => (r.value = e.detail.value)"
            >
              <view class="fc-picker wide">{{ r.value || '选择日期' }} ›</view>
            </picker>
            <input
              v-else-if="['int', 'decimal'].includes(fieldOf(r.field)?.data_type)"
              v-model="r.value" type="digit" class="fc-input" placeholder="数值"
            />
            <input v-else v-model="r.value" class="fc-input" placeholder="筛选值" />
          </view>
        </template>
        <view class="add-field sm" @click="b.filters.rules.push({ field: '', op: 'eq', value: null })">+ 添加筛选</view>
      </view>
    </view>

    <view class="add-blocks">
      <text class="ab" @click="addBlock('stat')">+ 统计卡片</text>
      <text class="ab" @click="addBlock('chart')">+ 图表</text>
      <text class="ab" @click="addBlock('table')">+ 明细表</text>
      <text class="ab" @click="addBlock('text')">+ 文本</text>
    </view>

    <!-- 查看端自助筛选字段 -->
    <view class="form-item">
      <view class="label">查看筛选（可选）</view>
      <view class="chip-row">
        <text
          v-for="f in tableFields" :key="f.field_name"
          class="chip" :class="{ on: form.filter_fields.includes(f.field_name) }"
          @click="toggleFilterField(f.field_name)"
        >{{ f.label }}</text>
      </view>
      <view class="lbl-sm" style="margin-top: 8rpx">查看报表时可按这些字段自助过滤，不改动模板配置</view>
    </view>

    <!-- 定时推送 -->
    <view class="form-item">
      <view class="label">定时推送（可选）</view>
      <view class="radio-row" style="margin-bottom: 16rpx">
        <view class="radio sm" :class="{ active: !form.schedule.type }" @click="form.schedule.type = ''">不定时</view>
        <view class="radio sm" :class="{ active: form.schedule.type === 'interval' }" @click="form.schedule.type = 'interval'">每隔 N 分钟</view>
        <view class="radio sm" :class="{ active: form.schedule.type === 'cron' }" @click="form.schedule.type = 'cron'">cron</view>
      </view>
      <template v-if="form.schedule.type">
        <input v-if="form.schedule.type === 'interval'" v-model="form.schedule.minutes" type="number" class="fc-input" placeholder="分钟数" />
        <view v-else class="fc-row">
          <input v-model="form.schedule.expr" class="fc-input" placeholder="分 时 日 月 周" />
          <text class="preset" @click="form.schedule.expr = '0 9 * * 1'">每周一9点</text>
          <text class="preset" @click="form.schedule.expr = '0 9 1 * *'">每月1号9点</text>
        </view>
        <input v-model="form.push.recipients" class="fc-input" style="margin-top: 12rpx" placeholder="收件邮箱，多个用逗号分隔" />
        <view v-for="(wh, i) in form.push.webhooks" :key="i" class="fc-row" style="margin-top: 12rpx">
          <text
            class="chip" :class="{ on: true }"
            @click="wh.type = wh.type === 'wecom' ? 'dingtalk' : wh.type === 'dingtalk' ? 'custom' : 'wecom'"
          >{{ WEBHOOK_LABELS[wh.type] || wh.type }}</text>
          <input v-model="wh.url" class="fc-input" style="flex: 1" placeholder="机器人 Webhook 地址" />
          <text class="bc-op del" @click="form.push.webhooks.splice(i, 1)">删</text>
        </view>
        <view class="add-field sm" @click="form.push.webhooks.push({ type: 'wecom', url: '' })">+ 添加群机器人（企微/钉钉，点标签切换）</view>
        <view class="fc-row" style="margin-top: 12rpx">
          <text class="chip" :class="{ on: form.push.formats.includes('html_inline') }" @click="toggleFormat('html_inline')">邮件正文</text>
          <text class="chip" :class="{ on: form.push.formats.includes('xlsx') }" @click="toggleFormat('xlsx')">Excel 附件</text>
          <text class="lbl">启用推送</text>
          <switch :checked="form.enabled" @change="(e) => (form.enabled = e.detail.value)" style="transform: scale(.8)" />
        </view>
      </template>
    </view>

    <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存报表' }}</button>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { aiAssistReport, createReport, getReport, getTable, listTables, updateReport } from '../../api'

const BLOCK_LABELS = { stat: '统计卡片', chart: '图表', table: '明细表', text: '文本' }
const WEBHOOK_LABELS = { wecom: '企业微信', dingtalk: '钉钉', custom: '自定义' }
const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]
const STAT_AGGS = [
  { value: 'count', label: '计数' }, { value: 'count_distinct', label: '去重计数' },
  { value: 'sum', label: '求和' }, { value: 'avg', label: '平均值' },
  { value: 'max', label: '最大值' }, { value: 'min', label: '最小值' }, { value: 'ratio', label: '占比%' },
]
const CHART_AGGS = STAT_AGGS.filter((a) => a.value !== 'ratio')
const CHART_TYPES = [['bar', '柱状图'], ['line', '折线图'], ['pie', '饼图']]
const GROUP_KINDS = [{ value: 'field', label: '按字段分组' }, { value: 'day', label: '按日' }, { value: 'week', label: '按周' }, { value: 'month', label: '按月' }]
const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']
const OPS = {
  text: [['eq', '等于'], ['ne', '不等于'], ['contains', '包含'], ['startswith', '开头是'], ['null', '为空'], ['not_null', '不为空']],
  number: [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'], ['null', '为空'], ['not_null', '不为空']],
  date: [['eq', '等于'], ['gte', '不早于'], ['lte', '不晚于'], ['today', '当天'], ['past_days', '过去 N 天'], ['older_than_days', '早于 N 天前'], ['within_days', '未来 N 天内'], ['null', '为空'], ['not_null', '不为空']],
  bool: [['eq', '等于'], ['null', '为空'], ['not_null', '不为空']],
  select: [['eq', '等于'], ['ne', '不等于'], ['in', '属于'], ['null', '为空'], ['not_null', '不为空']],
}

const editId = ref(null)
const tables = ref([])
const tableIndex = ref(-1)
const tableFields = ref([])
const fieldOptions = ref([])
const saving = ref(false)
const aiDesc = ref('')
const aiGenerating = ref(false)
const aiNotes = ref('')

const form = ref(blank())

function blank() {
  return {
    name: '', enabled: false,
    range: { mode: 'this_week', date_field: 'created_at', start: null, end: null },
    blocks: [],
    filter_fields: [],
    schedule: { type: '', minutes: '60', expr: '0 9 * * 1' },
    push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [] },
  }
}

onLoad(async (q) => {
  editId.value = q.id ? Number(q.id) : null
  uni.setNavigationBarTitle({ title: editId.value ? '编辑报表' : '新建报表' })
  try {
    tables.value = await listTables()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
  if (editId.value) {
    try {
      await fillForm(await getReport(editId.value))
    } catch (e) {
      uni.showToast({ title: e.message, icon: 'none' })
    }
  }
})

async function fillForm(t) {
  form.value = {
    name: t.name, enabled: t.enabled,
    range: { mode: 'this_week', date_field: 'created_at', start: null, end: null, ...(t.range || {}) },
    blocks: (t.blocks || []).map((b) => ({
      ...b,
      filters: { logic: 'AND', ...(b.filters || {}), rules: (b.filters?.rules || []).map((r) => ({ ...r })) },
    })),
    filter_fields: [...(t.filter_fields || [])],
    schedule: { type: '', minutes: '60', expr: '0 9 * * 1', ...(t.schedule || {}) },
    push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [], ...(t.push || {}) },
  }
  tableIndex.value = tables.value.findIndex((x) => x.id === t.table_id)
  await loadFields(t.table_id)
}

async function loadFields(tid) {
  tableFields.value = []
  if (tid) {
    const t = await getTable(tid).catch(() => null)
    if (t) tableFields.value = t.fields
  }
  fieldOptions.value = [
    ...tableFields.value.map((f) => ({ field_name: f.field_name, label: f.label })),
    { field_name: 'created_at', label: '创建时间' },
    { field_name: 'updated_at', label: '更新时间' },
  ]
}

function onTableChange(e) {
  tableIndex.value = Number(e.detail.value)
  form.value.blocks = []
  loadFields(tables.value[tableIndex.value].id)
}

const dateFieldOptions = computed(() => [
  { value: 'created_at', label: '创建时间' },
  { value: 'updated_at', label: '更新时间' },
  ...tableFields.value.filter((f) => ['date', 'datetime'].includes(f.data_type)).map((f) => ({ value: f.field_name, label: f.label })),
])
const dateFieldLabel = computed(() => dateFieldOptions.value.find((o) => o.value === form.value.range.date_field)?.label || '创建时间')
const numericFields = computed(() => tableFields.value.filter((f) => ['int', 'decimal'].includes(f.data_type)))
const statBlocks = computed(() => form.value.blocks.filter((b) => b.type === 'stat'))
const allColumns = computed(() => [
  { value: 'id', label: 'ID' },
  ...tableFields.value.map((f) => ({ value: f.field_name, label: f.label })),
  { value: 'created_at', label: '创建时间' },
  { value: 'updated_at', label: '更新时间' },
])

function fieldOf(name) {
  if (name === 'created_at' || name === 'updated_at') return { field_name: name, data_type: 'datetime', widget: 'datetime-picker' }
  if (name === 'id') return { field_name: 'id', data_type: 'int', widget: 'number' }
  return tableFields.value.find((f) => f.field_name === name)
}

function fieldLabel(name) {
  if (!name) return ''
  return fieldOf(name)?.label || { created_at: '创建时间', updated_at: '更新时间', id: 'ID' }[name] || name
}

function columnLabel(name) {
  return allColumns.value.find((c) => c.value === name)?.label || '默认按ID'
}

function aggLabel(v) {
  return STAT_AGGS.find((a) => a.value === v)?.label || v
}

function needsField(agg) {
  return agg !== 'count' && agg !== 'ratio'
}

function aggFields(agg) {
  // 去重计数可用任意字段；其余数值聚合只能选数值字段
  return agg === 'count_distinct' ? tableFields.value : numericFields.value
}

function onAggChange(b, agg) {
  b.agg = agg
  if (!needsField(agg)) b.field = null
}

function toggleFilterField(fn) {
  const arr = form.value.filter_fields
  const i = arr.indexOf(fn)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(fn)
}

function groupFields(kind) {
  if (kind === 'field') return tableFields.value
  return tableFields.value.filter((f) => ['date', 'datetime'].includes(f.data_type))
    .concat([{ field_name: 'created_at', label: '创建时间' }, { field_name: 'updated_at', label: '更新时间' }])
}

function onGroupKind(b, e) {
  b.group.kind = GROUP_KINDS[Number(e.detail.value)].value
  b.group.field = null
}

function opsFor(fieldName) {
  const f = fieldOf(fieldName)
  const raw = !f ? OPS.text
    : f.widget === 'select' ? OPS.select
    : f.data_type === 'bool' ? OPS.bool
    : ['date', 'datetime'].includes(f.data_type) ? OPS.date
    : ['int', 'decimal'].includes(f.data_type) ? OPS.number
    : OPS.text
  return raw.map(([value, label]) => ({ value, label }))
}

function opLabel(r) {
  return opsFor(r.field).find((o) => o.value === r.op)?.label || r.op || '操作'
}

function selectOptions(f) {
  return (f?.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
}

let blockSeq = 0
function nextBlockId() {
  const existing = new Set(form.value.blocks.map((b) => b.id))
  do { blockSeq += 1 } while (existing.has(`b${blockSeq}`))
  return `b${blockSeq}`
}

function addBlock(type) {
  const base = { id: nextBlockId(), type, title: '', filters: { logic: 'AND', rules: [] } }
  if (type === 'stat') Object.assign(base, { agg: 'count', field: null })
  if (type === 'chart') Object.assign(base, { chart_type: 'bar', group: { kind: 'field', field: null }, agg: 'count', field: null, top_n: '8' })
  if (type === 'table') Object.assign(base, { columns: [], sort_by: 'created_at', sort_order: 'desc', limit: '100' })
  if (type === 'text') Object.assign(base, { content: '' })
  form.value.blocks.push(base)
}

function moveBlock(i, dir) {
  const arr = form.value.blocks
  if (i + dir < 0 || i + dir >= arr.length) return
  const [b] = arr.splice(i, 1)
  arr.splice(i + dir, 0, b)
}

function toggleColumn(b, col) {
  const i = b.columns.indexOf(col)
  if (i >= 0) b.columns.splice(i, 1)
  else b.columns.push(col)
}

function toggleFormat(f) {
  const arr = form.value.push.formats
  const i = arr.indexOf(f)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(f)
}

async function aiGenerate() {
  if (tableIndex.value < 0) return uni.showToast({ title: '请先选择数据表', icon: 'none' })
  if (!aiDesc.value.trim()) return uni.showToast({ title: '请描述报表需求', icon: 'none' })
  aiGenerating.value = true
  uni.showLoading({ title: 'AI 设计中…', mask: true })
  try {
    const r = await aiAssistReport(tables.value[tableIndex.value].id, aiDesc.value.trim())
    aiNotes.value = r.notes || ''
    if (!form.value.name.trim()) form.value.name = r.name
    form.value.range = { ...r.range, start: null, end: null }
    form.value.blocks = r.blocks.map((b) => ({ ...b, filters: b.filters || { logic: 'AND', rules: [] } }))
    uni.showToast({ title: '已生成，可继续调整', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
    aiGenerating.value = false
  }
}

async function save() {
  const f = form.value
  if (!f.name.trim()) return uni.showToast({ title: '请填写报表名称', icon: 'none' })
  if (tableIndex.value < 0) return uni.showToast({ title: '请选择数据表', icon: 'none' })
  if (!f.blocks.length) return uni.showToast({ title: '请至少添加一个区块', icon: 'none' })
  if (f.schedule.type && !f.push.recipients.trim()
      && !(f.push.webhooks || []).some((w) => (w.url || '').trim())) {
    return uni.showToast({ title: '定时推送需要至少一个渠道（邮箱或群机器人）', icon: 'none' })
  }
  const payload = {
    name: f.name.trim(),
    table_id: tables.value[tableIndex.value].id,
    enabled: f.schedule.type ? f.enabled : false,
    range: f.range,
    blocks: f.blocks.map((b) => ({
      ...b,
      top_n: b.top_n !== undefined ? Number(b.top_n) || 8 : undefined,
      limit: b.limit !== undefined ? Number(b.limit) || 100 : undefined,
      filters: { logic: b.filters.logic, rules: (b.filters.rules || []).filter((r) => r.field && r.op) },
    })),
    filter_fields: f.filter_fields || [],
    schedule: f.schedule.type === 'interval'
      ? { type: 'interval', minutes: Number(f.schedule.minutes) || 60 }
      : f.schedule.type === 'cron'
        ? { type: 'cron', expr: f.schedule.expr }
        : {},
    push: f.schedule.type
      ? { ...f.push, webhooks: (f.push.webhooks || []).filter((w) => (w.url || '').trim()) }
      : {},
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateReport(editId.value, payload)
    } else {
      await createReport(payload)
    }
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 600)
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    saving.value = false
  }
}
</script>

<style>
.page { padding: 24rpx; padding-bottom: 60rpx; }
.ai-box { background: #faf5ff; border: 1rpx solid #e9d5ff; border-radius: 16rpx; padding: 20rpx; margin-bottom: 16rpx; }
.ai-textarea { font-size: 26rpx; color: #303133; width: 100%; min-height: 100rpx; }
.ai-btn {
  margin-top: 12rpx; text-align: center; background: linear-gradient(135deg, #7c3aed, #a855f7);
  color: #fff; font-size: 28rpx; padding: 14rpx 0; border-radius: 32rpx;
}
.ai-notes { font-size: 22rpx; color: #e6a23c; margin-top: 12rpx; }
.form-item { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.label { font-size: 26rpx; color: #606266; margin-bottom: 12rpx; }
.required { color: #f56c6c; }
.input { font-size: 30rpx; color: #303133; }
.textarea { font-size: 26rpx; color: #303133; width: 100%; min-height: 120rpx; }
.picker-value { font-size: 30rpx; color: #303133; padding: 8rpx 0; }
.placeholder { color: #c0c4cc; }
.radio-row { display: flex; gap: 12rpx; flex-wrap: wrap; }
.radio { font-size: 26rpx; color: #606266; border: 1rpx solid #dcdfe6; border-radius: 32rpx; padding: 12rpx 28rpx; }
.radio.sm { font-size: 24rpx; padding: 8rpx 24rpx; }
.radio.active { background: #409eff; border-color: #409eff; color: #fff; }
.sec-title { font-size: 26rpx; color: #909399; margin: 8rpx 0 12rpx; }
.block-card { background: #fff; border-radius: 16rpx; padding: 20rpx 24rpx; margin-bottom: 12rpx; }
.bc-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; }
.bc-tag { font-size: 22rpx; color: #fff; border-radius: 8rpx; padding: 4rpx 14rpx; background: #909399; flex-shrink: 0; }
.tag-stat { background: #67c23a; }
.tag-chart { background: #409eff; }
.tag-table { background: #e6a23c; }
.bc-title { flex: 1; font-size: 28rpx; font-weight: 600; color: #303133; }
.bc-op { font-size: 26rpx; color: #409eff; padding: 4rpx 10rpx; }
.bc-op.del { color: #f56c6c; }
.bc-op.dim { color: #c0c4cc; }
.fc-row { display: flex; gap: 12rpx; align-items: center; margin-bottom: 12rpx; flex-wrap: wrap; }
.fc-picker { font-size: 24rpx; color: #409eff; border: 1rpx solid #b3d8ff; border-radius: 8rpx; padding: 10rpx 16rpx; max-width: 300rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fc-picker.wide { flex: 1; }
.fc-input { flex: 1; font-size: 26rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 8rpx; padding: 12rpx 16rpx; }
.lbl { font-size: 26rpx; color: #606266; width: 140rpx; }
.lbl-sm { font-size: 24rpx; color: #909399; }
.chip-row { display: flex; gap: 10rpx; flex-wrap: wrap; margin-top: 8rpx; }
.chip { font-size: 22rpx; color: #606266; background: #f5f7fa; border-radius: 8rpx; padding: 8rpx 18rpx; }
.chip.on { background: #409eff; color: #fff; }
.bc-filters { border-top: 1rpx dashed #e4e7ed; padding-top: 12rpx; margin-top: 4rpx; }
.add-field { text-align: center; color: #409eff; font-size: 26rpx; border: 1rpx dashed #b3d8ff; border-radius: 12rpx; padding: 14rpx; }
.add-field.sm { font-size: 24rpx; padding: 10rpx; }
.add-blocks { display: flex; gap: 16rpx; flex-wrap: wrap; margin-bottom: 20rpx; }
.ab { font-size: 26rpx; color: #409eff; border: 1rpx dashed #b3d8ff; border-radius: 12rpx; padding: 16rpx 24rpx; }
.preset { font-size: 22rpx; color: #409eff; background: #ecf5ff; border-radius: 24rpx; padding: 8rpx 18rpx; }
.save-btn { background: #409eff; color: #fff; border-radius: 48rpx; font-size: 32rpx; margin-top: 8rpx; }
.save-btn[disabled] { background: #a0cfff; }
</style>
