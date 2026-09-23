<template>
  <view class="page">
    <scroll-view scroll-x class="toolbar-scroll">
      <view class="toolbar">
        <view
          v-for="[v, l] in MODES" :key="v"
          class="mode-chip" :class="{ active: mode === v }"
          @click="changeMode(v)"
        >{{ l }}</view>
      </view>
    </scroll-view>
    <view v-if="mode === 'custom'" class="fc-row">
      <picker mode="date" :value="customStart" @change="(e) => { customStart = e.detail.value; maybeRun() }">
        <view class="fc-picker">{{ customStart || '开始日期' }} ›</view>
      </picker>
      <picker mode="date" :value="customEnd" @change="(e) => { customEnd = e.detail.value; maybeRun() }">
        <view class="fc-picker">{{ customEnd || '结束日期' }} ›</view>
      </picker>
    </view>

    <!-- 查看端自助筛选（模板声明了开放字段才显示） -->
    <view v-if="filterDefs.length" class="card filter-bar">
      <view class="lbl-sm" style="margin-bottom: 10rpx">筛选（不改模板配置）</view>
      <view v-for="f in filterDefs" :key="f.field_name" class="fc-row">
        <text class="lbl-sm filter-lbl">{{ f.label }}</text>
        <picker
          v-if="f.widget === 'select'" :range="selectOpts(f)"
          @change="(e) => setFilter(f, selectOpts(f)[Number(e.detail.value)])"
        >
          <view class="fc-picker wide">{{ filterValues[f.field_name] ?? '全部' }} ›</view>
        </picker>
        <picker
          v-else-if="f.data_type === 'bool'" :range="['是', '否']"
          @change="(e) => setFilter(f, Number(e.detail.value) === 0)"
        >
          <view class="fc-picker wide">{{ filterValues[f.field_name] === undefined ? '全部' : (filterValues[f.field_name] ? '是' : '否') }} ›</view>
        </picker>
        <template v-else-if="['date', 'datetime'].includes(f.data_type)">
          <picker mode="date" :value="filterValues[f.field_name]?.[0] || ''" @change="(e) => setDateFilter(f, 0, e.detail.value)">
            <view class="fc-picker wide">{{ filterValues[f.field_name]?.[0] || '开始' }} ›</view>
          </picker>
          <picker mode="date" :value="filterValues[f.field_name]?.[1] || ''" @change="(e) => setDateFilter(f, 1, e.detail.value)">
            <view class="fc-picker wide">{{ filterValues[f.field_name]?.[1] || '结束' }} ›</view>
          </picker>
        </template>
        <input
          v-else v-model="filterValues[f.field_name]" class="fc-input"
          :placeholder="['int', 'decimal'].includes(f.data_type) ? '等于数值' : '包含文本'" @confirm="run" @blur="run"
        />
      </view>
    </view>

    <view v-if="result" class="meta">{{ result.range.label }} · 生成于 {{ result.generated_at }}</view>

    <view v-if="loading" class="hint">生成中…</view>
    <template v-else-if="result">
      <!-- 统计卡片 -->
      <view v-if="statBlocks.length" class="stats">
        <view v-for="b in statBlocks" :key="b.id" class="stat">
          <view class="stat-title">{{ b.title }}</view>
          <view class="stat-value">{{ b.value }}<text v-if="b.agg === 'ratio'" class="stat-unit">%</text></view>
          <view v-if="b.compare" class="stat-compare">
            较上期
            <text v-if="b.compare.delta_pct !== null" :style="{ color: b.compare.delta >= 0 ? '#f56c6c' : '#67c23a' }">
              {{ b.compare.delta >= 0 ? '↑' : '↓' }}{{ Math.abs(b.compare.delta_pct) }}%
            </text>
            <text v-else>上期 {{ b.compare.prev }}，无基数</text>
          </view>
        </view>
      </view>

      <view v-for="b in otherBlocks" :key="b.id" class="card">
        <view class="block-title">{{ b.title }}</view>

        <template v-if="b.type === 'chart'">
          <UChart v-if="b.labels.length" :type="b.chart_type" :labels="b.labels" :values="b.values" :series="b.series" :stack="b.stack" />
          <view v-else class="hint" style="padding: 30rpx 0">该时间范围内暂无数据</view>
          <!-- 数据明细兜底 -->
          <view class="data-table">
            <view v-for="(l, i) in b.labels" :key="i" class="dt-row">
              <text class="dt-label">{{ l }}</text>
              <text class="dt-value">{{ seriesText(b, i) }}</text>
            </view>
          </view>
        </template>

        <template v-else-if="b.type === 'table'">
          <scroll-view scroll-x class="table-scroll">
            <view class="grid" :style="{ minWidth: b.columns.length * 180 + 'rpx' }">
              <view class="grid-row grid-head">
                <text v-for="c in b.columns" :key="c.prop" class="grid-cell">{{ c.label }}</text>
              </view>
              <view v-for="(r, ri) in b.rows" :key="ri" class="grid-row">
                <text v-for="c in b.columns" :key="c.prop" class="grid-cell">{{ r[c.prop] ?? '—' }}</text>
              </view>
            </view>
          </scroll-view>
          <view v-if="b.truncated" class="truncated">共 {{ b.total }} 条，仅显示前 {{ b.rows.length }} 条</view>
        </template>

        <template v-else-if="b.type === 'text'">
          <view class="text-block">{{ b.content }}</view>
        </template>
      </view>
    </template>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getReport, getTable, runReport } from '../../api'
import UChart from '../../components/UChart.vue'

const MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]

const tplId = ref(null)
const mode = ref(null)   // null = 跟随模板默认口径
const customStart = ref('')
const customEnd = ref('')
const result = ref(null)
const loading = ref(false)
const filterDefs = ref([])       // 开放筛选字段的元数据
const filterValues = ref({})     // field_name -> 控件值

const statBlocks = computed(() => (result.value?.blocks || []).filter((b) => b.type === 'stat'))
const otherBlocks = computed(() => (result.value?.blocks || []).filter((b) => b.type !== 'stat'))

onLoad((q) => {
  tplId.value = Number(q.id)
  uni.setNavigationBarTitle({ title: q.name ? decodeURIComponent(q.name) : '报表详情' })
  run()
  // 加载模板声明的查看端筛选字段
  getReport(tplId.value).then(async (t) => {
    if (!t.filter_fields?.length) return
    const meta = await getTable(t.table_id).catch(() => null)
    if (!meta) return
    filterDefs.value = t.filter_fields
      .map((fn) => meta.fields.find((f) => f.field_name === fn))
      .filter(Boolean)
  }).catch(() => {})
})

function selectOpts(f) {
  return (f?.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
}

// 图表数据明细兜底：多系列时拼成 "系列名 值，系列名 值"
function seriesText(b, i) {
  const ss = b.series?.length ? b.series : [{ name: '', values: b.values }]
  if (ss.length === 1) return ss[0].values[i]
  return ss.map((s) => `${s.name} ${s.values[i]}`).join('，')
}

function setFilter(f, v) {
  filterValues.value[f.field_name] = v
  run()
}

function setDateFilter(f, idx, v) {
  const cur = Array.isArray(filterValues.value[f.field_name]) ? [...filterValues.value[f.field_name]] : ['', '']
  cur[idx] = v
  filterValues.value[f.field_name] = cur
  if (cur[0] && cur[1]) run()
}

function currentFilters() {
  const rules = []
  for (const f of filterDefs.value) {
    const v = filterValues.value[f.field_name]
    if (v === undefined || v === null || v === '') continue
    if (['date', 'datetime'].includes(f.data_type)) {
      if (!Array.isArray(v) || (!v[0] && !v[1])) continue
      if (v[0]) rules.push({ field: f.field_name, op: 'gte', value: v[0] })
      if (v[1]) rules.push({ field: f.field_name, op: 'lte', value: v[1] })
    } else if (f.widget === 'select' || f.data_type === 'bool' || ['int', 'decimal'].includes(f.data_type)) {
      rules.push({ field: f.field_name, op: 'eq', value: v })
    } else {
      rules.push({ field: f.field_name, op: 'contains', value: v })
    }
  }
  return rules.length ? { logic: 'AND', rules } : undefined
}

function maybeRun() {
  if (customStart.value && customEnd.value) run()
}

async function run() {
  loading.value = true
  try {
    let range
    if (mode.value) {
      range = { mode: mode.value }
      if (mode.value === 'custom') {
        if (!customStart.value || !customEnd.value) { loading.value = false; return }
        range.start = customStart.value
        range.end = customEnd.value
      }
    }
    result.value = await runReport(tplId.value, range, currentFilters())
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function changeMode(v) {
  mode.value = v
  if (v !== 'custom') run()
}
</script>

<style>
.page { padding: 24rpx; }
.toolbar { display: flex; gap: 12rpx; margin-bottom: 12rpx; }
.toolbar-scroll { white-space: nowrap; }
.toolbar .mode-chip { display: inline-block; }
.mode-chip {
  font-size: 24rpx; color: #606266; background: #fff; border-radius: 28rpx; padding: 8rpx 24rpx;
}
.mode-chip.active { background: #409eff; color: #fff; }
.fc-row { display: flex; gap: 12rpx; align-items: center; margin-bottom: 12rpx; flex-wrap: wrap; }
.fc-picker { font-size: 24rpx; color: #409eff; border: 1rpx solid #b3d8ff; border-radius: 8rpx; padding: 10rpx 16rpx; }
.fc-picker.wide { flex: 1; }
.fc-input { flex: 1; font-size: 26rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 8rpx; padding: 12rpx 16rpx; }
.lbl-sm { font-size: 24rpx; color: #909399; }
.filter-lbl { width: 150rpx; flex-shrink: 0; }
.filter-bar { padding-top: 16rpx; }
.stat-unit { font-size: 24rpx; font-weight: 400; color: #909399; }
.stat-compare { font-size: 22rpx; color: #909399; margin-top: 6rpx; }
.meta { font-size: 22rpx; color: #909399; margin-bottom: 16rpx; }
.hint { text-align: center; color: #909399; padding: 60rpx 0; font-size: 28rpx; }
.stats { display: flex; flex-wrap: wrap; gap: 16rpx; margin-bottom: 16rpx; }
.stat {
  background: #fff; border-radius: 16rpx; padding: 20rpx 32rpx; min-width: 200rpx; flex: 1;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05);
}
.stat-title { font-size: 24rpx; color: #909399; }
.stat-value { font-size: 44rpx; font-weight: 600; color: #303133; margin-top: 6rpx; }
.card {
  background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 20rpx;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05);
}
.block-title { font-size: 30rpx; font-weight: 600; color: #303133; margin-bottom: 16rpx; }
.data-table { margin-top: 16rpx; border-top: 1rpx solid #f0f0f0; }
.dt-row { display: flex; justify-content: space-between; padding: 10rpx 0; font-size: 26rpx; border-bottom: 1rpx solid #f7f7f7; }
.dt-label { color: #606266; }
.dt-value { color: #303133; font-weight: 500; }
.table-scroll { width: 100%; }
.grid-row { display: flex; border-bottom: 1rpx solid #f0f0f0; }
.grid-head { background: #f5f7fa; }
.grid-cell {
  width: 180rpx; flex-shrink: 0; padding: 12rpx 16rpx; font-size: 24rpx; color: #303133;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.truncated { font-size: 22rpx; color: #909399; margin-top: 12rpx; }
.text-block { font-size: 28rpx; color: #606266; line-height: 1.7; }
</style>
