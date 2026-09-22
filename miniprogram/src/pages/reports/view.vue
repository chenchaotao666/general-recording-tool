<template>
  <view class="page">
    <view class="toolbar">
      <view
        v-for="[v, l] in MODES" :key="v"
        class="mode-chip" :class="{ active: mode === v }"
        @click="changeMode(v)"
      >{{ l }}</view>
    </view>
    <view v-if="result" class="meta">{{ result.range.label }} · 生成于 {{ result.generated_at }}</view>

    <view v-if="loading" class="hint">生成中…</view>
    <template v-else-if="result">
      <!-- 统计卡片 -->
      <view v-if="statBlocks.length" class="stats">
        <view v-for="b in statBlocks" :key="b.id" class="stat">
          <view class="stat-title">{{ b.title }}</view>
          <view class="stat-value">{{ b.value }}</view>
        </view>
      </view>

      <view v-for="b in otherBlocks" :key="b.id" class="card">
        <view class="block-title">{{ b.title }}</view>

        <template v-if="b.type === 'chart'">
          <UChart v-if="b.labels.length" :type="b.chart_type" :labels="b.labels" :values="b.values" />
          <view v-else class="hint" style="padding: 30rpx 0">该时间范围内暂无数据</view>
          <!-- 数据明细兜底 -->
          <view class="data-table">
            <view v-for="(l, i) in b.labels" :key="i" class="dt-row">
              <text class="dt-label">{{ l }}</text>
              <text class="dt-value">{{ b.values[i] }}</text>
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
import { runReport } from '../../api'
import UChart from '../../components/UChart.vue'

const MODES = [['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月']]

const tplId = ref(null)
const mode = ref(null)   // null = 跟随模板默认口径
const result = ref(null)
const loading = ref(false)

const statBlocks = computed(() => (result.value?.blocks || []).filter((b) => b.type === 'stat'))
const otherBlocks = computed(() => (result.value?.blocks || []).filter((b) => b.type !== 'stat'))

onLoad((q) => {
  tplId.value = Number(q.id)
  uni.setNavigationBarTitle({ title: q.name ? decodeURIComponent(q.name) : '报表详情' })
  run()
})

async function run() {
  loading.value = true
  try {
    result.value = await runReport(tplId.value, mode.value ? { mode: mode.value } : undefined)
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function changeMode(v) {
  mode.value = v
  run()
}
</script>

<style>
.page { padding: 24rpx; }
.toolbar { display: flex; gap: 12rpx; margin-bottom: 12rpx; }
.mode-chip {
  font-size: 24rpx; color: #606266; background: #fff; border-radius: 28rpx; padding: 8rpx 24rpx;
}
.mode-chip.active { background: #409eff; color: #fff; }
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
