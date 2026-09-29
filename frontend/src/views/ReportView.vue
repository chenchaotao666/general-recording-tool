<template>
  <div v-loading="loading">
    <div class="page-header">
      <div>
        <el-button text :icon="ArrowLeft" @click="$router.push('/reports')">返回</el-button>
        <h2 style="display: inline-block; margin-left: 8px">{{ result?.name || '报表' }}</h2>
        <span v-if="result" style="margin-left: 12px; color: #909399; font-size: 13px">
          {{ result.range.label }} · 生成于 {{ result.generated_at }}
        </span>
      </div>
      <div>
        <el-button :icon="Grid" @click="$router.push(`/reports/${tplId}/layout`)">设计</el-button>
        <el-button :icon="Download" @click="exportFile('xlsx')">导出 Excel</el-button>
        <el-button :icon="Download" @click="exportFile('html')">导出 HTML</el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-radio-group v-model="rangeMode" size="small" @change="onModeChange">
        <el-radio-button v-for="[v, l] in RANGE_MODES" :key="v" :value="v">{{ l }}</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-if="rangeMode === 'custom'" v-model="customRange" type="daterange" size="small"
        value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" style="margin-left: 10px"
      />
      <el-button size="small" type="primary" :loading="loading" style="margin-left: 10px" @click="run">重新生成</el-button>
    </div>

    <!-- 查看端自助筛选（模板声明了开放字段才显示） -->
    <div v-if="filterDefs.length" class="toolbar filter-bar">
      <span style="color: #909399; font-size: 13px">筛选</span>
      <template v-for="f in filterDefs" :key="f.field_name">
        <el-select
          v-if="f.widget === 'select'" v-model="filterValues[f.field_name]" :placeholder="f.label"
          clearable size="small" style="width: 140px" @change="run"
        >
          <el-option v-for="o in selectOpts(f)" :key="String(o)" :label="o" :value="o" />
        </el-select>
        <el-select
          v-else-if="f.data_type === 'bool'" v-model="filterValues[f.field_name]" :placeholder="f.label"
          clearable size="small" style="width: 110px" @change="run"
        >
          <el-option label="是" :value="true" /><el-option label="否" :value="false" />
        </el-select>
        <el-date-picker
          v-else-if="['date', 'datetime'].includes(f.data_type)" v-model="filterValues[f.field_name]"
          type="daterange" value-format="YYYY-MM-DD" size="small"
          :start-placeholder="`${f.label}起`" :end-placeholder="`${f.label}止`" style="width: 240px" @change="run"
        />
        <el-input-number
          v-else-if="['int', 'decimal'].includes(f.data_type)" v-model="filterValues[f.field_name]"
          :placeholder="f.label" size="small" controls-position="right" style="width: 130px" @change="run"
        />
        <el-input
          v-else v-model="filterValues[f.field_name]" :placeholder="f.label"
          clearable size="small" style="width: 160px" @change="run"
        />
      </template>
      <el-button v-if="hasFilter" size="small" text @click="clearFilters">清空筛选</el-button>
    </div>

    <template v-if="result">
      <!-- 图表联动中的过滤条件 -->
      <div v-if="linkList.length" class="link-bar">
        <span style="color: #909399; font-size: 13px">联动</span>
        <el-tag
          v-for="l in linkList" :key="l.field" closable size="small" type="warning" effect="plain"
          @close="clearLink(l.field)"
        >{{ l.field }} = {{ l.label }}</el-tag>
        <el-button size="small" text @click="clearAllLinks">清除全部</el-button>
      </div>
      <ReportDashboard
        :blocks="result.blocks" :layout="result.layout" drillable :drill-paths="drillPaths"
        @drill="onDashDrill" @link="onDashLink" @viewer-filter="onViewerFilter"
        @drill-level="onDrillLevel" @drill-back="clearOverride" @jump="onJump"
        @swap-pivot="onSwapPivot" @page="onTablePage" @table-sort="onTableSort"
      />
      <el-empty v-if="!result.blocks.length" description="该模板还没有区块，去编辑添加" />
    </template>

    <!-- 图表下钻明细 -->
    <el-dialog v-model="drill.visible" :title="drill.title" width="80%" top="8vh">
      <div v-loading="drill.loading">
        <el-table :data="drillPageRows" size="small" border max-height="55vh">
          <el-table-column
            v-for="c in drill.columns" :key="c.prop" :prop="c.prop" :label="c.label"
            show-overflow-tooltip
          />
        </el-table>
        <div class="drill-foot">
          <el-pagination
            v-if="drill.rows.length > DRILL_PAGE_SIZE" v-model:current-page="drillPage"
            small background layout="total, prev, pager, next" :page-size="DRILL_PAGE_SIZE" :total="drill.rows.length"
          />
          <span v-if="drill.truncated" class="drill-truncated">
            共 {{ drill.total }} 条，仅加载前 {{ drill.rows.length }} 条
          </span>
        </div>
        <el-empty v-if="!drill.loading && !drill.rows.length" description="该分组暂无记录" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Grid } from '@element-plus/icons-vue'
import { reportExportUrl, runReport, drillReport, getReport, getTable } from '../api'
import ReportDashboard from '../components/ReportDashboard.vue'

const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]

const route = useRoute()
const router = useRouter()
// 响应式 tplId：同组件跳转（报表间跳转）时 params/query 变化但组件复用，需监听路由重新初始化
const tplId = computed(() => route.params.id)

const result = ref(null)
const loading = ref(false)
const rangeMode = ref('this_week')
const customRange = ref(null)
const tplBlocks = ref([])   // 模板区块配置（层级钻取/行列互换的覆盖基准）

// ---------- 图表联动 ----------
const linkFilters = ref({})   // field -> {value, label}
const linkList = computed(() => Object.entries(linkFilters.value).map(([field, v]) => ({ field, ...v })))

function onDashLink({ field, value, label }) {
  // 再点同一个分组 = 取消联动
  if (linkFilters.value[field]?.value === value) {
    delete linkFilters.value[field]
  } else {
    linkFilters.value = { ...linkFilters.value, [field]: { value, label } }
  }
  run()
}

function clearLink(field) {
  delete linkFilters.value[field]
  run()
}

function clearAllLinks() {
  linkFilters.value = {}
  run()
}

const currentLinks = computed(() =>
  Object.entries(linkFilters.value).map(([field, v]) => ({ field, value: v.value }))
)

// ---------- 筛选组件块 ----------
const blockFilters = ref({})    // block_id -> rules[]

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
  run()
}

// 工具条筛选 + 筛选组件块 合并（恒 AND）
function mergedFilters() {
  const rules = [...(currentFilters()?.rules || []), ...Object.values(blockFilters.value).flat()]
  return rules.length ? { logic: 'AND', rules } : null
}

// ---------- 图表下钻 ----------
const drill = ref({ visible: false, loading: false, title: '', columns: [], rows: [], total: 0, truncated: false })

// 下钻明细分页（客户端，每页 50 条；后端截断时提示只加载了前 N 条）
const DRILL_PAGE_SIZE = 50
const drillPage = ref(1)
const drillPageRows = computed(() =>
  drill.value.rows.slice((drillPage.value - 1) * DRILL_PAGE_SIZE, drillPage.value * DRILL_PAGE_SIZE)
)

async function openDrill(title, payload) {
  drill.value = { visible: true, loading: true, columns: [], rows: [], total: 0, truncated: false, title }
  drillPage.value = 1
  try {
    const res = await drillReport(tplId.value, {
      ...payload,
      range: currentRange() || { mode: rangeMode.value }, filters: mergedFilters(), links: currentLinks.value,
    })
    Object.assign(drill.value, { loading: false, ...res })
  } catch (e) {
    drill.value.loading = false
    drill.value.visible = false
    ElMessage.error(e.message)
  }
}

function onDashDrill({ title, ...payload }) {
  openDrill(title, payload)
}

function currentRange() {
  const r = { mode: rangeMode.value }
  if (rangeMode.value === 'custom') {
    if (!customRange.value?.length) return null
    r.start = customRange.value[0]
    r.end = customRange.value[1]
  }
  return r
}

// ---------- 查看端自助筛选 ----------
const filterDefs = ref([])        // 开放筛选字段的元数据
const filterValues = ref({})      // field_name -> 控件值

function selectOpts(f) {
  return (f?.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
}

const hasFilter = computed(() =>
  Object.values(filterValues.value).some((v) => v != null && v !== '' && !(Array.isArray(v) && !v.length))
)

function currentFilters() {
  const rules = []
  for (const f of filterDefs.value) {
    const v = filterValues.value[f.field_name]
    if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue
    if (['date', 'datetime'].includes(f.data_type)) {
      rules.push({ field: f.field_name, op: 'gte', value: v[0] })
      rules.push({ field: f.field_name, op: 'lte', value: v[1] })
    } else if (f.widget === 'select' || f.data_type === 'bool' || ['int', 'decimal'].includes(f.data_type)) {
      rules.push({ field: f.field_name, op: 'eq', value: v })
    } else {
      rules.push({ field: f.field_name, op: 'contains', value: v })
    }
  }
  return rules.length ? { logic: 'AND', rules } : null
}

function clearFilters() {
  filterValues.value = {}
  run()
}

// ---------- 明细表服务端分页 ----------
const TABLE_PAGE_SIZE = 50
const tablePages = ref({})   // block_id -> 当前页（改筛选/口径时重置回第 1 页）

function blockPagesParam() {
  const out = {}
  for (const b of tplBlocks.value.length ? tplBlocks.value : (result.value?.blocks || [])) {
    if (b.type === 'table') out[b.id] = { page: tablePages.value[b.id] || 1, page_size: TABLE_PAGE_SIZE }
  }
  return Object.keys(out).length ? out : null
}

function onTablePage({ block_id, page }) {
  tablePages.value = { ...tablePages.value, [block_id]: page }
  run(true)
}

// 明细表点列头排序：走 block_overrides 服务端排序（排序后回第 1 页）
function onTableSort({ block_id, sort_by, sort_order }) {
  const o = { ...blockOverrides.value }
  if (sort_by) {
    o[block_id] = { ...o[block_id], sort_by, sort_order }
  } else if (o[block_id]) {
    delete o[block_id].sort_by
    delete o[block_id].sort_order
    if (!Object.keys(o[block_id]).length) delete o[block_id]
  }
  blockOverrides.value = o
  const p = { ...tablePages.value }
  delete p[block_id]
  tablePages.value = p
  run(true)
}

// ---------- 层级钻取 / 透视表行列互换（临时覆盖块配置，不落库） ----------
const blockOverrides = ref({})  // block_id -> {group?, row?, col?, filters?}
const drillPaths = ref({})      // block_id -> [{field, value, label}]

function overridesParam() {
  return Object.keys(blockOverrides.value).length ? blockOverrides.value : null
}

function clearOverride(block_id) {
  const o = { ...blockOverrides.value }
  const p = { ...drillPaths.value }
  delete o[block_id]
  delete p[block_id]
  blockOverrides.value = o
  drillPaths.value = p
  run(true)
}

function onDrillLevel({ block_id, field, value, label }) {
  const b = tplBlocks.value.find((x) => x.id === block_id)
  const dd = b?.drill_down?.field
  if (!dd) return
  drillPaths.value = { ...drillPaths.value, [block_id]: [{ field, value, label }] }
  blockOverrides.value = {
    ...blockOverrides.value,
    [block_id]: {
      group: { kind: 'field', field: dd },
      filters: { logic: 'AND', rules: [...(b.filters?.rules || []), { field, op: 'eq', value }] },
    },
  }
  run(true)
}

function onSwapPivot(block_id) {
  if (blockOverrides.value[block_id]?.row) return clearOverride(block_id)   // 已互换，再点还原
  const b = tplBlocks.value.find((x) => x.id === block_id)
  if (!b?.row || !b?.col) return
  blockOverrides.value = { ...blockOverrides.value, [block_id]: { row: b.col, col: b.row } }
  run(true)
}

// ---------- 报表间跳转：带着点击的分组值跳目标报表（作为其联动过滤） ----------
function onJump({ report_id, field, value, label }) {
  router.push({
    path: `/reports/${report_id}/view`,
    query: { link_field: field, link_value: String(value), link_label: label },
  })
}

async function run(keepPages = false) {
  const range = currentRange()
  if (!range) return ElMessage.warning('请选择自定义日期范围')
  if (!keepPages) tablePages.value = {}   // 筛选/口径/联动变化：明细表回第 1 页
  loading.value = true
  try {
    result.value = await runReport(tplId.value, range, mergedFilters(), currentLinks.value,
      undefined, blockPagesParam(), overridesParam())
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function onModeChange() {
  if (rangeMode.value !== 'custom') run()
}

function exportFile(format) {
  const range = currentRange() || { mode: rangeMode.value }
  window.open(reportExportUrl(tplId.value, { format, ...range, filters: mergedFilters() }), '_blank')
}

async function init() {
  // 初始口径跟随模板默认值；工具条回填模板口径
  loading.value = true
  // 重新进入时清空交互状态（联动/筛选/钻取/分页都随之复位）
  blockOverrides.value = {}
  drillPaths.value = {}
  tablePages.value = {}
  linkFilters.value = {}
  try {
    const t = await getReport(tplId.value)
    tplBlocks.value = t.blocks || []
    // 报表间跳转入口：?link_field=xx&link_value=yy 作为初始联动过滤
    if (route.query.link_field && route.query.link_value != null) {
      linkFilters.value = {
        [route.query.link_field]: { value: route.query.link_value, label: route.query.link_label || route.query.link_value },
      }
    }
    result.value = await runReport(tplId.value, null, null, currentLinks.value, undefined, blockPagesParam())
    rangeMode.value = t.range?.mode || 'this_week'
    if (rangeMode.value === 'custom' && t.range?.start && t.range?.end) {
      customRange.value = [t.range.start, t.range.end]
    }
    if (t.filter_fields?.length) {
      const meta = await getTable(t.table_id)
      filterDefs.value = t.filter_fields
        .map((fn) => meta.fields.find((f) => f.field_name === fn))
        .filter(Boolean)
    } else {
      filterDefs.value = []
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(init)

// 同组件路由变化（报表间跳转：/reports/6/view?link_... → /reports/8/view?...）：重新初始化
watch(() => route.fullPath, () => {
  if (route.path === `/reports/${route.params.id}/view`) init()
})
</script>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px 0; }
.toolbar :deep(.el-radio-group) { flex-wrap: wrap; row-gap: 6px; }
.filter-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.link-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
/* 下钻明细底栏：分页居右 + 截断提示居左 */
.drill-foot { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.drill-foot .el-pagination { margin-left: auto; }
.drill-truncated { font-size: 12px; color: #909399; }
</style>
