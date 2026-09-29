<template>
  <div class="share-page" v-loading="loading">
    <!-- 密码验证 -->
    <el-card v-if="needPassword" class="pwd-card">
      <div class="title">此内容受密码保护</div>
      <el-input v-model="password" type="password" show-password placeholder="请输入访问密码" @keyup.enter="load" />
      <el-button type="primary" style="width: 100%; margin-top: 12px" @click="load">访问</el-button>
      <div v-if="error" class="error">{{ error }}</div>
    </el-card>

    <template v-else-if="data">
      <!-- 表 -->
      <template v-if="data.resource_type === 'table'">
        <div class="page-header">
          <h2>{{ data.label }}</h2>
          <span class="total">共 {{ data.total }} 条</span>
        </div>
        <el-table :data="data.records" border stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column
            v-for="f in data.fields" :key="f.field_name"
            :prop="f.field_name" :label="f.label" show-overflow-tooltip min-width="110"
          >
            <template #default="{ row }">{{ fmt(f, row[f.field_name]) }}</template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="data.total > data.page_size"
          v-model:current-page="page" :page-size="data.page_size" :total="data.total"
          layout="prev, pager, next" style="margin-top: 14px" @current-change="load"
        />
      </template>

      <!-- 报表 -->
      <template v-else>
        <div class="page-header"><h2>{{ data.label }}</h2></div>
        <div class="meta">{{ data.report.range.label }} · 生成于 {{ data.report.generated_at }}</div>
        <!-- 开放交互的链接：查看者可切换口径；筛选组件块也可用了 -->
        <div v-if="data.allow_interact" class="share-toolbar">
          <el-radio-group v-model="rangeMode" size="small" @change="onModeChange">
            <el-radio-button v-for="[v, l] in RANGE_MODES" :key="v" :value="v">{{ l }}</el-radio-button>
          </el-radio-group>
        </div>
        <ReportDashboard
          :blocks="data.report.blocks" :layout="data.report.layout"
          :filterable="!!data.allow_interact" @viewer-filter="onViewerFilter" @page="onTablePage"
          @table-sort="onTableSort"
        />
      </template>
    </template>

    <el-result v-else-if="error" icon="warning" :title="error" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ReportDashboard from '../components/ReportDashboard.vue'

const route = useRoute()
const token = route.params.token

const loading = ref(false)
const needPassword = ref(false)
const password = ref('')
const error = ref('')
const data = ref(null)
const page = ref(1)

// 开放交互的分享：口径切换 + 筛选组件块（与查看页同一套 viewer-filter 协议）
const RANGE_MODES = [
  ['', '默认口径'], ['today', '今天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'], ['this_year', '今年'],
]
const rangeMode = ref('')
const blockFilters = ref({})   // block_id -> rules[]

// 明细表服务端分页（纯展示层参数，未开放交互的链接也可用）
const TABLE_PAGE_SIZE = 50
const tablePages = ref({})   // block_id -> 当前页

function onTablePage({ block_id, page }) {
  tablePages.value = { ...tablePages.value, [block_id]: page }
  load()
}

// 点列头排序（纯展示层参数，后端只放行排序键）
const tableSorts = ref({})   // block_id -> {sort_by, sort_order}

function onTableSort({ block_id, sort_by, sort_order }) {
  const s = { ...tableSorts.value }
  if (sort_by) s[block_id] = { sort_by, sort_order }
  else delete s[block_id]
  tableSorts.value = s
  const p = { ...tablePages.value }
  delete p[block_id]
  tablePages.value = p
  load()
}

function blockPagesParam() {
  const out = {}
  for (const b of data.value?.report?.blocks || []) {
    if (b.type === 'table') out[b.id] = { page: tablePages.value[b.id] || 1, page_size: TABLE_PAGE_SIZE }
  }
  return Object.keys(out).length ? out : null
}

function onModeChange() {
  tablePages.value = {}   // 口径变化回第 1 页
  load()
}

function onViewerFilter({ block_id, field, value, data_type, widget, dataset }) {
  if (!field) return
  const empty = value == null || value === '' || (Array.isArray(value) && !value.length)
  if (empty) {
    delete blockFilters.value[block_id]
  } else if (['date', 'datetime'].includes(data_type)) {
    blockFilters.value[block_id] = [
      { dataset, field, op: 'gte', value: value[0] },
      { dataset, field, op: 'lte', value: value[1] },
    ]
  } else if (widget === 'select' || data_type === 'bool' || ['int', 'decimal'].includes(data_type)) {
    blockFilters.value[block_id] = [{ dataset, field, op: 'eq', value }]
  } else {
    blockFilters.value[block_id] = [{ dataset, field, op: 'contains', value }]
  }
  tablePages.value = {}   // 筛选变化回第 1 页
  load()
}

function mergedFilters() {
  const rules = Object.values(blockFilters.value).flat()
  return rules.length ? { logic: 'AND', rules } : null
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ page: page.value, page_size: 50 })
    if (password.value) params.set('password', password.value)
    // 仅开放交互的链接会生效（后端按链接的 allow_interact 判定，未开放时忽略）
    if (rangeMode.value) params.set('mode', rangeMode.value)
    const f = mergedFilters()
    if (f) params.set('filters', JSON.stringify(f))
    const bp = blockPagesParam()
    if (bp) params.set('block_pages', JSON.stringify(bp))
    if (Object.keys(tableSorts.value).length) params.set('block_overrides', JSON.stringify(tableSorts.value))
    const res = await fetch(`/api/share/${token}?${params}`)
    if (res.status === 401) {
      needPassword.value = true
      return
    }
    if (!res.ok) {
      const d = await res.json().catch(() => ({}))
      error.value = d.detail || `加载失败（${res.status}）`
      return
    }
    needPassword.value = false
    data.value = await res.json()
  } catch (e) {
    error.value = '无法连接服务器'
  } finally {
    loading.value = false
  }
}

function fmt(f, val) {
  if (val === null || val === undefined || val === '') return '—'
  if (f.data_type === 'bool') return val ? '是' : '否'
  if (f.widget === 'select') {
    const opts = f.options?.options || []
    const hit = opts.find((o) => (typeof o === 'object' ? o.value : o) === val)
    return typeof hit === 'object' ? hit.label : (hit ?? val)
  }
  return String(val)
}

onMounted(load)
</script>

<style scoped>
.share-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.pwd-card { max-width: 360px; margin: 120px auto; text-align: center; }
.pwd-card .title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.error { color: #f56c6c; font-size: 13px; margin-top: 12px; }
.total { color: #909399; font-size: 13px; }
.meta { color: #909399; font-size: 12px; margin-bottom: 14px; }
.share-toolbar { margin-bottom: 12px; }
/* 口径按钮多时换行而不是横向滚动（overflow-x 会连带裁掉按钮底部边框） */
.share-toolbar :deep(.el-radio-group) { flex-wrap: wrap; row-gap: 6px; }
.block { margin-bottom: 16px; }
</style>
