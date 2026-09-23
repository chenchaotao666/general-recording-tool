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
      <!-- 统计卡片 -->
      <div v-if="statBlocks.length" class="stats">
        <div v-for="b in statBlocks" :key="b.id" class="stat-card">
          <div class="stat-title">{{ b.title }}</div>
          <div class="stat-value">{{ b.value }}<span v-if="b.agg === 'ratio'" class="stat-unit">%</span></div>
          <div v-if="b.compare" class="stat-compare">
            较上期
            <span v-if="b.compare.delta_pct !== null" :class="b.compare.delta >= 0 ? 'up' : 'down'">
              {{ b.compare.delta >= 0 ? '↑' : '↓' }}{{ Math.abs(b.compare.delta_pct) }}%
            </span>
            <span v-else style="color: #909399">上期 {{ b.compare.prev }}，无对比基数</span>
          </div>
        </div>
      </div>

      <!-- 其余区块按模板顺序 -->
      <div v-for="b in otherBlocks" :key="b.id" class="block">
        <h3>{{ b.title }}</h3>
        <template v-if="b.type === 'chart'">
          <div :ref="(el) => chartRef(b.id, el)" class="chart" />
        </template>
        <template v-else-if="b.type === 'table'">
          <el-table :data="b.rows" size="small" border max-height="480">
            <el-table-column
              v-for="c in b.columns" :key="c.prop" :prop="c.prop" :label="c.label"
              show-overflow-tooltip
            />
          </el-table>
          <div v-if="b.truncated" style="font-size: 12px; color: #909399; margin-top: 6px">
            共 {{ b.total }} 条，仅显示前 {{ b.rows.length }} 条
          </div>
        </template>
        <template v-else-if="b.type === 'text'">
          <div class="text-block">{{ b.content }}</div>
        </template>
      </div>
      <el-empty v-if="!result.blocks.length" description="该模板还没有区块，去编辑添加" />
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { reportExportUrl, runReport, getReport, getTable } from '../api'

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TitleComponent, TooltipComponent, CanvasRenderer])

const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]

const route = useRoute()
const tplId = route.params.id

const result = ref(null)
const loading = ref(false)
const rangeMode = ref('this_week')
const customRange = ref(null)
const chartEls = new Map()
let charts = []

const statBlocks = computed(() => (result.value?.blocks || []).filter((b) => b.type === 'stat'))
const otherBlocks = computed(() => (result.value?.blocks || []).filter((b) => b.type !== 'stat'))

function chartRef(id, el) {
  if (el) chartEls.set(id, el)
}

function renderCharts() {
  charts.forEach((c) => c.dispose())
  charts = []
  for (const b of result.value?.blocks || []) {
    if (b.type !== 'chart') continue
    const el = chartEls.get(b.id)
    if (!el) continue
    const ch = echarts.init(el)
    let option
    if (b.chart_type === 'pie') {
      option = {
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{ type: 'pie', radius: ['35%', '65%'], data: b.labels.map((l, i) => ({ name: l, value: b.values[i] })) }],
      }
    } else {
      const seriesList = (b.series?.length ? b.series : [{ name: '', values: b.values }])
      const stack = b.stack && seriesList.length > 1 ? 'total' : undefined
      option = {
        tooltip: { trigger: 'axis' },
        legend: seriesList.length > 1 ? { bottom: 0 } : undefined,
        grid: { left: 48, right: 24, top: 24, bottom: seriesList.length > 1 ? 56 : 48 },
        xAxis: { type: 'category', data: b.labels },
        yAxis: { type: 'value' },
        series: seriesList.map((s) => ({
          name: s.name,
          type: b.chart_type === 'area' ? 'line' : b.chart_type,
          data: s.values,
          barMaxWidth: 40,
          smooth: true,
          ...(stack ? { stack } : {}),
          ...(b.chart_type === 'area' ? { areaStyle: {} } : {}),
        })),
      }
    }
    ch.setOption(option)
    charts.push(ch)
  }
}

function onResize() {
  charts.forEach((c) => c.resize())
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

async function run() {
  const range = currentRange()
  if (!range) return ElMessage.warning('请选择自定义日期范围')
  loading.value = true
  try {
    result.value = await runReport(tplId, range, currentFilters())
    await nextTick()
    renderCharts()
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
  window.open(reportExportUrl(tplId, { format, ...range, filters: currentFilters() }), '_blank')
}

onMounted(async () => {
  // 初始口径跟随模板默认值；工具条回填模板口径
  loading.value = true
  try {
    const [r, t] = await Promise.all([runReport(tplId), getReport(tplId)])
    result.value = r
    rangeMode.value = t.range?.mode || 'this_week'
    if (rangeMode.value === 'custom' && t.range?.start && t.range?.end) {
      customRange.value = [t.range.start, t.range.end]
    }
    if (t.filter_fields?.length) {
      const meta = await getTable(t.table_id)
      filterDefs.value = t.filter_fields
        .map((fn) => meta.fields.find((f) => f.field_name === fn))
        .filter(Boolean)
    }
    await nextTick()
    renderCharts()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  charts.forEach((c) => c.dispose())
})
</script>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px 0; }
.toolbar :deep(.el-radio-group) { flex-wrap: wrap; row-gap: 6px; }
.stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.stat-card {
  background: #fff; border-radius: 8px; padding: 16px 28px; min-width: 150px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .06);
}
.stat-title { font-size: 13px; color: #909399; }
.stat-value { font-size: 30px; font-weight: 600; margin-top: 4px; color: #303133; }
.stat-unit { font-size: 16px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-compare { font-size: 12px; color: #909399; margin-top: 6px; }
.stat-compare .up { color: #f56c6c; }
.stat-compare .down { color: #67c23a; }
.filter-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.block { background: #fff; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0, 0, 0, .06); }
.block h3 { margin: 0 0 12px; font-size: 15px; }
.chart { width: 100%; height: 340px; }
.text-block { color: #606266; line-height: 1.8; white-space: pre-wrap; }
</style>
