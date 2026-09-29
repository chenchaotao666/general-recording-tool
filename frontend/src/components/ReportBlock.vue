<template>
  <!-- 单个报表区块（统计卡/图表/透视表/明细表/文本）。fill=填满父容器（栅格模式），否则按内容自然高度（流式）。 -->
  <div class="rblock" :class="{ fill }">
    <template v-if="block.type === 'stat'">
      <div class="stat-card">
        <div class="stat-title">
          {{ block.title }}<span v-if="block.range_badge" class="range-badge">{{ block.range_badge }}</span>
        </div>
        <div class="stat-value">{{ block.value }}<span v-if="block.agg === 'ratio'" class="stat-unit">%</span></div>
        <div v-if="block.compare" class="stat-compare">
          {{ block.compare.type === 'yoy' ? '较去年同期' : '较上期' }}
          <span v-if="block.compare.delta_pct !== null" :class="block.compare.delta >= 0 ? 'up' : 'down'">
            {{ block.compare.delta >= 0 ? '↑' : '↓' }}{{ Math.abs(block.compare.delta_pct) }}%
          </span>
          <span v-else style="color: #909399">对比期 {{ block.compare.prev }}，无对比基数</span>
        </div>
      </div>
    </template>

    <template v-else-if="block.type === 'chart'">
      <div class="block-card">
        <h3>{{ block.title }}<span v-if="block.range_badge" class="range-badge">{{ block.range_badge }}</span></h3>
        <!-- 层级钻取面包屑：处于下钻层时显示，点击返回上级 -->
        <div v-if="drillPath.length" class="drill-path">
          <el-tag
            v-for="(s, i) in drillPath" :key="i" size="small" type="warning" effect="plain" closable
            @close="emit('drill-back', block.id)"
          >{{ s.label }}</el-tag>
          <el-button link type="primary" size="small" @click="emit('drill-back', block.id)">返回上级</el-button>
        </div>
        <div ref="chartEl" class="chart" />
        <div v-if="drillable && block.chart_type !== 'gauge'" class="drill-hint">{{ chartHint }}</div>
      </div>
    </template>

    <template v-else-if="block.type === 'filter'">
      <div class="block-card filter-card">
        <div class="filter-label">{{ block.title }}</div>
        <el-select
          v-if="block.widget === 'select'" :model-value="modelValue" :placeholder="block.title"
          clearable size="small" style="width: 100%" @update:model-value="onFilterInput"
        >
          <el-option v-for="o in filterOptions" :key="String(o)" :label="o" :value="o" />
        </el-select>
        <el-select
          v-else-if="block.data_type === 'bool'" :model-value="modelValue" :placeholder="block.title"
          clearable size="small" style="width: 100%" @update:model-value="onFilterInput"
        >
          <el-option label="是" :value="true" /><el-option label="否" :value="false" />
        </el-select>
        <el-date-picker
          v-else-if="['date', 'datetime'].includes(block.data_type)" :model-value="modelValue"
          type="daterange" value-format="YYYY-MM-DD" size="small" style="width: 100%"
          start-placeholder="起" end-placeholder="止" @update:model-value="onFilterInput"
        />
        <el-input-number
          v-else-if="['int', 'decimal'].includes(block.data_type)" :model-value="modelValue"
          :placeholder="block.title" size="small" controls-position="right" style="width: 100%"
          @update:model-value="onFilterInput"
        />
        <el-input
          v-else :model-value="modelValue" :placeholder="block.title"
          clearable size="small" @update:model-value="onFilterInput"
        />
      </div>
    </template>

    <template v-else-if="block.type === 'pivot'">
      <div class="block-card">
        <h3>{{ block.title }}<span v-if="block.range_badge" class="range-badge">{{ block.range_badge }}</span></h3>
        <div class="pivot-tools">
          <el-button link type="primary" size="small" :icon="Switch" title="行列维度互换" @click="emit('swap-pivot', block.id)">互换</el-button>
          <el-button link size="small" :type="heatOn ? 'primary' : 'info'" title="色阶：数值越大底色越深，最大值为深蓝反白" @click="heatOn = !heatOn">色阶</el-button>
        </div>
        <el-table
          :key="heatOn ? 'heat' : 'plain'"
          :data="pivotRows" size="small" border :max-height="fill ? undefined : 480"
          :height="fill ? tableHeight : undefined"
          :cell-style="heatOn ? pivotHeatStyle : undefined"
          @cell-click="onPivotCellClick" @sort-change="onPivotSort"
        >
          <el-table-column label="行＼列" prop="__label" fixed show-overflow-tooltip />
          <el-table-column
            v-for="(cl, ci) in block.col_labels" :key="ci" :label="cl" :prop="'c' + ci"
            align="right" sortable="custom"
          />
          <el-table-column v-if="block.totals" label="合计" prop="__rt" align="right" sortable="custom" />
        </el-table>
        <div v-if="drillable" class="drill-hint">点击数值单元格可查看明细</div>
      </div>
    </template>

    <template v-else-if="block.type === 'table'">
      <div class="block-card">
        <h3>{{ block.title }}<span v-if="block.range_badge" class="range-badge">{{ block.range_badge }}</span></h3>
        <el-table
          :data="tableRows" size="small" border :max-height="fill ? undefined : 480"
          :height="fill ? tableHeight : undefined" @sort-change="onTableSort"
        >
          <el-table-column
            v-for="c in block.columns" :key="c.prop" :prop="c.prop" :label="c.label"
            show-overflow-tooltip sortable="custom"
          />
        </el-table>
        <div class="table-foot">
          <!-- 服务端分页（block.page 存在）：翻页上抛由父级带 block_pages 重跑；否则客户端分页 -->
          <el-pagination
            v-if="block.page ? block.total > block.page_size : (block.rows?.length || 0) > TABLE_PAGE_SIZE"
            :current-page="block.page || tablePage" small background layout="total, prev, pager, next"
            :page-size="block.page_size || TABLE_PAGE_SIZE" :total="block.total"
            @current-change="onTablePage"
          />
          <div v-if="block.truncated" class="truncated-hint">
            共 {{ block.total }} 条，仅加载前 {{ block.rows.length }} 条
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="block.type === 'text'">
      <div class="block-card">
        <h3 v-if="block.title">{{ block.title }}</h3>
        <div class="text-block">{{ block.content }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Switch } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { BarChart, FunnelChart, GaugeChart, LineChart, PieChart } from 'echarts/charts'
import {
  DataZoomInsideComponent, DataZoomSliderComponent, GridComponent, LegendComponent,
  TitleComponent, TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, FunnelChart, GaugeChart, LineChart, PieChart,
  DataZoomInsideComponent, DataZoomSliderComponent, GridComponent, LegendComponent,
  TitleComponent, TooltipComponent, CanvasRenderer,
])

const props = defineProps({
  block: { type: Object, required: true },
  drillable: { type: Boolean, default: false },
  fill: { type: Boolean, default: false },
  modelValue: { type: [String, Number, Boolean, Array], default: null },  // filter 块的控件值
  drillPath: { type: Array, default: () => [] },  // 层级钻取面包屑 [{field, label}]，非空表示处于下钻层
})
const emit = defineEmits(['drill', 'link', 'update:modelValue', 'drill-level', 'drill-back', 'jump', 'swap-pivot', 'page', 'table-sort'])

// ---------- 筛选组件 ----------
// 级联：后端按其它筛选条件收缩可选值（available），未给则用字段全量 options
const filterOptions = computed(() =>
  (props.block.available || props.block.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
)

function onFilterInput(v) {
  emit('update:modelValue', v)
}

// 图表点击提示文案：按点击行为区分（下钻层内不再提示）
const chartHint = computed(() => {
  const b = props.block
  if (props.drillPath.length) return '已下钻一层，点上方标签返回上级'
  if (b.on_click === 'link' && b.group_field) return '点击图表可联动过滤其他区块'
  if (b.on_click === 'jump' && b.group_field) return '点击图表可跳转查看关联报表'
  if (b.drill_down && b.group_field) return '点击图表可下钻到下一层分组'
  return '点击图表可查看该分组明细'
})

// ---------- 图表 ----------
const chartEl = ref(null)
let chart = null
let ro = null

// ---------- 明细表分页（服务端优先：block.page 存在时翻页上抛父级重跑；否则客户端分页） ----------
const TABLE_PAGE_SIZE = 50
const tablePage = ref(1)
const tablePageRows = computed(() => {
  const rows = [...(props.block.rows || [])]
  const { prop, order } = tableSort.value
  if (prop && order) {
    // 客户端排序兜底（非服务端分页场景：导出外的全量返回）
    const dir = order === 'ascending' ? 1 : -1
    rows.sort((x, y) => {
      const a = x[prop]
      const z = y[prop]
      if (a == null && z == null) return 0
      if (a == null) return 1
      if (z == null) return -1
      const cmp = typeof a === 'number' && typeof z === 'number' ? a - z : String(a).localeCompare(String(z), 'zh')
      return cmp * dir
    })
  }
  return rows.slice((tablePage.value - 1) * TABLE_PAGE_SIZE, tablePage.value * TABLE_PAGE_SIZE)
})
const tableRows = computed(() => (props.block.page ? (props.block.rows || []) : tablePageRows.value))

function onTablePage(p) {
  if (props.block.page) {
    emit('page', { block_id: props.block.id, page: p })
  } else {
    tablePage.value = p
  }
}

// 点列头排序：服务端分页时必须上抛（客户端排序只能排当前页）；非服务端分页的兜底场景做客户端排序
const tableSort = ref({ prop: '', order: '' })

function onTableSort({ prop, order }) {
  tableSort.value = { prop: prop || '', order: order || '' }
  if (props.block.page) {
    emit('table-sort', {
      block_id: props.block.id,
      sort_by: order ? prop : null,
      sort_order: order === 'ascending' ? 'asc' : 'desc',
    })
  }
}

// fill 模式下表格高度 = 容器高 - 标题/底栏（分页条显示时让出高度）
const tableHeight = computed(() => {
  if (!props.fill) return undefined
  const hasPager = props.block.type === 'table'
    && (props.block.page ? props.block.total > (props.block.page_size || TABLE_PAGE_SIZE)
                         : (props.block.rows?.length || 0) > TABLE_PAGE_SIZE)
  const extra = hasPager ? 98 : 64
  return `calc(100% - ${extra}px)`
})

function buildOption(b) {
  if (b.chart_type === 'gauge') {
    return {
      series: [{
        type: 'gauge', min: 0, max: b.max || 100,
        progress: { show: true, width: 14 },
        axisLine: { lineStyle: { width: 14 } },
        axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
        pointer: { length: '60%' },
        anchor: { show: true, size: 12 },
        detail: { valueAnimation: true, fontSize: 26, offsetCenter: [0, '70%'] },
        data: [{ value: b.value }],
      }],
    }
  }
  if (b.chart_type === 'pie') {
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{ type: 'pie', radius: ['35%', '65%'], data: b.labels.map((l, i) => ({ name: l, value: b.values[i] })) }],
    }
  }
  if (b.chart_type === 'funnel') {
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c}' },
      legend: { bottom: 0 },
      series: [{
        type: 'funnel', left: '10%', width: '80%', sort: 'descending', gap: 2,
        label: { show: true, position: 'inside', formatter: '{b}: {c}' },
        data: b.labels.map((l, i) => ({ name: l, value: b.values[i] })),
      }],
    }
  }
  const seriesList = (b.series?.length ? b.series : [{ name: '', values: b.values }])
  const stack = b.stack && seriesList.length > 1 ? 'total' : undefined
  const isMixed = b.chart_type === 'mixed'
  const isPct = b.unit === '%'
  // 分组点多时给缩放：底部滑块 + 图表内拖拽平移/Shift+滚轮缩放（滚轮不直接缩放，避免抢占页面滚动）
  const many = (b.labels?.length || 0) > 12
  const dataZoom = many
    ? [
      { type: 'inside', zoomOnMouseWheel: 'shift', moveOnMouseWheel: false },
      { type: 'slider', height: 16, bottom: seriesList.length > 1 ? 26 : 6 },
    ]
    : undefined
  // 组合图双轴：折线系列（含对比系列）落右轴；占比时坐标轴/tooltip 带 %
  const valueAxis = {
    type: 'value',
    ...(isPct ? { axisLabel: { formatter: '{value}%' } } : {}),
  }
  return {
    ...(dataZoom ? { dataZoom } : {}),
    tooltip: {
      trigger: 'axis',
      ...(isPct ? { valueFormatter: (v) => (v == null ? '—' : `${v}%`) } : {}),
    },
    legend: seriesList.length > 1 ? { bottom: 0 } : undefined,
    grid: {
      left: 48, right: isMixed ? 48 : 24, top: 24,
      bottom: (seriesList.length > 1 ? 56 : 48) + (many ? 22 : 0),
    },
    xAxis: { type: 'category', data: b.labels },
    yAxis: isMixed ? [valueAxis, { ...valueAxis, splitLine: { show: false } }] : valueAxis,
    series: seriesList.map((s, i) => {
      const isCmp = !!s.compare   // 对比系列（环比/同比）：固定虚线灰折线
      const type = isCmp ? 'line' : isMixed ? (s.chart || 'bar') : (b.chart_type === 'area' ? 'line' : b.chart_type)
      return {
        name: s.name,
        type,
        data: s.values,
        ...(isMixed ? { yAxisIndex: type === 'line' ? 1 : 0 } : {}),
        barMaxWidth: 40,
        smooth: true,
        ...(isCmp ? { lineStyle: { type: 'dashed' }, itemStyle: { color: '#909399' } } : {}),
        ...(stack && !isCmp && !isMixed ? { stack } : {}),
        ...(b.chart_type === 'area' ? { areaStyle: {} } : {}),
      }
    }),
  }
}

function onChartClick(p) {
  if (!props.drillable || p.componentType !== 'series' || p.dataIndex == null) return
  const b = props.block
  if (b.chart_type === 'gauge') return
  // 层级钻取状态：点击不再弹明细（口径已换成下一层分组，明细接口不认临时覆盖），用面包屑返回
  if (props.drillPath.length) return
  const groupIndex = p.dataIndex
  // 联动模式：点分组 → 等值过滤同报表其他区块（"其他"桶/空值桶不联动，回退下钻）
  if (b.on_click === 'link' && b.group_field) {
    const key = b.keys?.[groupIndex]
    if (key !== null && key !== undefined) {
      emit('link', { field: b.group_field, value: key, label: b.labels[groupIndex] })
      return
    }
  }
  // 跳转其他报表：带着点击的分组值作为目标报表的联动过滤
  if (b.on_click === 'jump' && b.group_field && b.jump_report_id) {
    const key = b.keys?.[groupIndex]
    if (key !== null && key !== undefined) {
      emit('jump', { report_id: b.jump_report_id, field: b.group_field, value: key, label: b.labels[groupIndex] })
      return
    }
  }
  // 层级钻取：点分组 → 本块换成下一层分组字段（如 区域 → 城市）
  if (b.drill_down && b.group_field) {
    const key = b.keys?.[groupIndex]
    if (key !== null && key !== undefined) {
      emit('drill-level', { block_id: b.id, field: b.group_field, value: key, label: b.labels[groupIndex] })
      return
    }
  }
  // 二级分组图的系列是筛选维度；多指标图的系列只是指标，不影响记录集
  const seriesIndex = b.group2 && p.seriesIndex != null ? p.seriesIndex : null
  const seriesName = b.group2 ? b.series?.[p.seriesIndex]?.name : null
  emit('drill', {
    title: `${b.title} · ${b.labels[groupIndex]}${seriesName ? ` · ${seriesName}` : ''}`,
    block_id: b.id, group_index: groupIndex, series_index: seriesIndex,
  })
}

// ---------- 透视表 ----------
// 点击列头排序（客户端，合计行固定垫底不参与排序）
const pivotSort = ref({ prop: '', order: '' })

function onPivotSort({ prop, order }) {
  pivotSort.value = { prop: prop || '', order: order || '' }
}

const pivotRows = computed(() => {
  const b = props.block
  if (b.type !== 'pivot') return []
  const rows = b.row_labels.map((rl, i) => {
    const r = { __label: rl, __ri: i }
    b.col_labels.forEach((_, ci) => { r['c' + ci] = b.cells[i]?.[ci] })
    if (b.totals) r.__rt = b.row_totals[i]
    return r
  })
  const { prop, order } = pivotSort.value
  if (prop && order) {
    const dir = order === 'ascending' ? 1 : -1
    rows.sort((x, y) => ((x[prop] ?? -Infinity) - (y[prop] ?? -Infinity)) * dir)
  }
  if (b.totals) {
    const t = { __label: '合计', __ri: null }
    b.col_labels.forEach((_, ci) => { t['c' + ci] = b.col_totals[ci] })
    t.__rt = b.grand_total
    rows.push(t)
  }
  return rows
})

// 色阶：数值格按 min~max 归一化映射底色深度（0.12 ~ 0.87 透明度），最深格文字反白；
// 合计行/列不参与刻度（避免总量压扁），但着色时按边界值钳制
const heatOn = ref(false)
const heatScale = computed(() => {
  const b = props.block
  if (b.type !== 'pivot') return null
  const vals = []
  b.cells.forEach((r) => r.forEach((v) => { if (typeof v === 'number') vals.push(v) }))
  if (vals.length < 2) return null
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  return max === min ? null : { min, span: max - min }
})

function pivotHeatStyle({ row, column }) {
  const prop = column?.property
  if (!prop || prop === '__label') return {}
  const sc = heatScale.value
  if (!sc) return {}
  const v = row[prop]
  if (typeof v !== 'number') return {}
  const ratio = Math.min(Math.max((v - sc.min) / sc.span, 0), 1)
  if (ratio <= 0) return {}
  const style = { background: `rgba(64, 158, 255, ${(0.12 + ratio * 0.75).toFixed(3)})` }
  if (ratio > 0.55) style.color = '#fff'   // 深色底反白
  return style
}

// 点单元格下钻：数据格=行×列；合计列=整行；合计行=整列；总计格=全部
function onPivotCellClick(row, column) {
  if (!props.drillable) return
  const b = props.block
  const prop = column?.property
  if (!prop || prop === '__label') return
  const seriesIndex = prop === '__rt' ? null : Number(prop.slice(1))
  const groupIndex = row.__ri
  const rl = groupIndex === null ? '合计行' : b.row_labels[groupIndex]
  const cl = seriesIndex === null ? '合计' : b.col_labels[seriesIndex]
  emit('drill', {
    title: `${b.title} · ${rl} × ${cl}`,
    block_id: b.id, group_index: groupIndex, series_index: seriesIndex,
  })
}

function initChart() {
  if (props.block.type !== 'chart' || !chartEl.value) return
  if (!chart) {
    chart = echarts.init(chartEl.value)
    chart.on('click', onChartClick)
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(chartEl.value)
  }
  chart.setOption(buildOption(props.block), true)   // notMerge：数据/类型变化全量重绘
}

onMounted(initChart)

// 块数据更新（重新取数/草稿重绘）：模板插值天然响应，echarts 需要手动重绘
watch(() => props.block, async () => {
  tablePage.value = 1   // 数据换了明细表回到第一页
  await nextTick()   // 等类型分支渲染出对应容器
  if (props.block.type !== 'chart') {
    ro?.disconnect()
    ro = null
    chart?.dispose()
    chart = null
    return
  }
  initChart()
})

onBeforeUnmount(() => {
  ro?.disconnect()
  chart?.dispose()
})
</script>

<style scoped>
.rblock.fill { height: 100%; }
/* fill 模式必须 border-box：否则 height:100% + 上下 padding 32px 会溢出栅格行高，内容压到下面的块 */
.rblock.fill .block-card { height: 100%; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; }
.rblock.fill .block-card .chart { flex: 1; min-height: 0; }
.rblock.fill .stat-card { height: 100%; box-sizing: border-box; }

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

.block-card { background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0, 0, 0, .06); }
.block-card h3 { margin: 0 0 12px; font-size: 15px; }
.chart { width: 100%; height: 340px; }
.drill-hint { font-size: 12px; color: #c0c4cc; text-align: right; }
.drill-path { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.pivot-tools { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
.pivot-sort-hint { font-size: 12px; color: #c0c4cc; margin-left: 4px; }
.truncated-hint { font-size: 12px; color: #909399; }
/* 明细表底栏：分页居右 + 截断提示居左 */
.table-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 8px; }
.table-foot .truncated-hint { order: -1; }
.table-foot .el-pagination { margin-left: auto; }
.text-block { color: #606266; line-height: 1.8; white-space: pre-wrap; }
.range-badge {
  margin-left: 8px; font-size: 11px; font-weight: 400; color: #909399;
  background: #f0f2f5; border-radius: 4px; padding: 1px 6px; vertical-align: middle;
}
.filter-card { display: flex; align-items: center; gap: 10px; padding: 10px 16px; }
.filter-card .filter-label { flex-shrink: 0; font-size: 13px; color: #606266; }
/* fill（栅格）模式下 block-card 默认 flex-column，会把筛选 label 挤到控件上方——查看时 label 放左侧更紧凑 */
.rblock.fill .filter-card { flex-direction: row; }
/* 日期区间组件默认渲染偏高（45px），对齐到 small 控件的 24px */
.filter-card :deep(.el-date-editor.el-range-editor) { height: 24px !important; box-sizing: border-box; }
.rblock.fill .filter-card { height: 100%; box-sizing: border-box; }
</style>
