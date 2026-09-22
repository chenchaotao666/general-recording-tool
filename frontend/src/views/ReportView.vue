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
        <el-radio-button value="this_week">本周</el-radio-button>
        <el-radio-button value="last_week">上周</el-radio-button>
        <el-radio-button value="this_month">本月</el-radio-button>
        <el-radio-button value="last_month">上月</el-radio-button>
        <el-radio-button value="custom">自定义</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-if="rangeMode === 'custom'" v-model="customRange" type="daterange" size="small"
        value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" style="margin-left: 10px"
      />
      <el-button size="small" type="primary" :loading="loading" style="margin-left: 10px" @click="run">重新生成</el-button>
    </div>

    <template v-if="result">
      <!-- 统计卡片 -->
      <div v-if="statBlocks.length" class="stats">
        <div v-for="b in statBlocks" :key="b.id" class="stat-card">
          <div class="stat-title">{{ b.title }}</div>
          <div class="stat-value">{{ b.value }}</div>
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
import { reportExportUrl, runReport } from '../api'

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TitleComponent, TooltipComponent, CanvasRenderer])

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
      option = {
        tooltip: { trigger: 'axis' },
        grid: { left: 48, right: 24, top: 24, bottom: 48 },
        xAxis: { type: 'category', data: b.labels },
        yAxis: { type: 'value' },
        series: [{ type: b.chart_type, data: b.values, barMaxWidth: 40, smooth: true }],
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

async function run() {
  const range = currentRange()
  if (!range) return ElMessage.warning('请选择自定义日期范围')
  loading.value = true
  try {
    result.value = await runReport(tplId, range)
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
  window.open(reportExportUrl(tplId, { format, ...range }), '_blank')
}

onMounted(async () => {
  // 初始口径跟随模板默认值（run 接口缺省即模板口径），工具条显示本周仅作占位
  loading.value = true
  try {
    result.value = await runReport(tplId)
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
.toolbar { margin-bottom: 16px; }
.stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.stat-card {
  background: #fff; border-radius: 8px; padding: 16px 28px; min-width: 150px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .06);
}
.stat-title { font-size: 13px; color: #909399; }
.stat-value { font-size: 30px; font-weight: 600; margin-top: 4px; color: #303133; }
.block { background: #fff; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0, 0, 0, .06); }
.block h3 { margin: 0 0 12px; font-size: 15px; }
.chart { width: 100%; height: 340px; }
.text-block { color: #606266; line-height: 1.8; white-space: pre-wrap; }
</style>
