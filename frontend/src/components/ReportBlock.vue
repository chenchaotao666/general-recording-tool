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
          较上期
          <span v-if="block.compare.delta_pct !== null" :class="block.compare.delta >= 0 ? 'up' : 'down'">
            {{ block.compare.delta >= 0 ? '↑' : '↓' }}{{ Math.abs(block.compare.delta_pct) }}%
          </span>
          <span v-else style="color: #909399">上期 {{ block.compare.prev }}，无对比基数</span>
        </div>
      </div>
    </template>

    <template v-else-if="block.type === 'chart'">
      <div class="block-card">
        <h3>{{ block.title }}<span v-if="block.range_badge" class="range-badge">{{ block.range_badge }}</span></h3>
        <div ref="chartEl" class="chart" />
        <div v-if="drillable && block.chart_type !== 'gauge'" class="drill-hint">
          {{ block.on_click === 'link' && block.group_field ? '点击图表可联动过滤其他区块' : '点击图表可查看该分组明细' }}
        </div>
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
        <el-table
          :data="pivotRows" size="small" border :max-height="fill ? undefined : 480"
          :height="fill ? tableHeight : undefined"
          @cell-click="onPivotCellClick"
        >
          <el-table-column label="行＼列" prop="__label" fixed show-overflow-tooltip />
          <el-table-column v-for="(cl, ci) in block.col_labels" :key="ci" :label="cl" :prop="'c' + ci" align="right" />
          <el-table-column v-if="block.totals" label="合计" prop="__rt" align="right" />
        </el-table>
        <div v-if="drillable" class="drill-hint">点击数值单元格可查看明细</div>
      </div>
    </template>

    <template v-else-if="block.type === 'table'">
      <div class="block-card">
        <h3>{{ block.title }}<span v-if="block.range_badge" class="range-badge">{{ block.range_badge }}</span></h3>
        <el-table
          :data="block.rows" size="small" border :max-height="fill ? undefined : 480"
          :height="fill ? tableHeight : undefined"
        >
          <el-table-column
            v-for="c in block.columns" :key="c.prop" :prop="c.prop" :label="c.label"
            show-overflow-tooltip
          />
        </el-table>
        <div v-if="block.truncated" class="truncated-hint">
          共 {{ block.total }} 条，仅显示前 {{ block.rows.length }} 条
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
import * as echarts from 'echarts/core'
import { BarChart, GaugeChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GaugeChart, LineChart, PieChart, GridComponent, LegendComponent, TitleComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  block: { type: Object, required: true },
  drillable: { type: Boolean, default: false },
  fill: { type: Boolean, default: false },
  modelValue: { type: [String, Number, Boolean, Array], default: null },  // filter 块的控件值
})
const emit = defineEmits(['drill', 'link', 'update:modelValue'])

// ---------- 筛选组件 ----------
const filterOptions = computed(() =>
  (props.block.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
)

function onFilterInput(v) {
  emit('update:modelValue', v)
}

// ---------- 图表 ----------
const chartEl = ref(null)
let chart = null
let ro = null

// fill 模式下表格高度 = 容器高 - 标题/提示（约 64px）
const tableHeight = computed(() => (props.fill ? 'calc(100% - 64px)' : undefined))

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
  const seriesList = (b.series?.length ? b.series : [{ name: '', values: b.values }])
  const stack = b.stack && seriesList.length > 1 ? 'total' : undefined
  return {
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

function onChartClick(p) {
  if (!props.drillable || p.componentType !== 'series' || p.dataIndex == null) return
  const b = props.block
  if (b.chart_type === 'gauge') return
  const groupIndex = p.dataIndex
  // 联动模式：点分组 → 等值过滤同报表其他区块（"其他"桶/空值桶不联动，回退下钻）
  if (b.on_click === 'link' && b.group_field) {
    const key = b.keys?.[groupIndex]
    if (key !== null && key !== undefined) {
      emit('link', { field: b.group_field, value: key, label: b.labels[groupIndex] })
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
const pivotRows = computed(() => {
  const b = props.block
  if (b.type !== 'pivot') return []
  const rows = b.row_labels.map((rl, i) => {
    const r = { __label: rl, __ri: i }
    b.col_labels.forEach((_, ci) => { r['c' + ci] = b.cells[i]?.[ci] })
    if (b.totals) r.__rt = b.row_totals[i]
    return r
  })
  if (b.totals) {
    const t = { __label: '合计', __ri: null }
    b.col_labels.forEach((_, ci) => { t['c' + ci] = b.col_totals[ci] })
    t.__rt = b.grand_total
    rows.push(t)
  }
  return rows
})

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
.truncated-hint { font-size: 12px; color: #909399; margin-top: 6px; }
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
