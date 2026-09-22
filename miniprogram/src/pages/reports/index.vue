<template>
  <view class="page">
    <view class="header">
      <view class="total">共 {{ reports.length }} 个报表</view>
      <view class="add-btn" @click="uni.navigateTo({ url: '/pages/reports/edit' })">+ 新建报表</view>
    </view>
    <view v-if="loading" class="hint">加载中…</view>
    <view v-else-if="!reports.length" class="hint">还没有报表模板，请先在电脑端创建</view>
    <view v-for="r in reports" :key="r.id" class="card" @click="openView(r)">
      <view class="card-title">{{ r.name }}</view>
      <view class="card-sub">
        {{ r.table_label }} · {{ r.range_desc }} · {{ r.block_count }} 个区块
      </view>
      <view v-if="r.schedule?.type" class="card-sub">
        定时推送：{{ r.schedule.type === 'cron' ? r.schedule.expr : `每 ${r.schedule.minutes} 分钟` }}
        <text :style="{ color: r.enabled ? '#67c23a' : '#909399' }">{{ r.enabled ? ' · 已启用' : ' · 已停用' }}</text>
      </view>
      <view class="card-footer">
        <text class="foot-act" @click.stop="openView(r)">查看</text>
        <text class="foot-act" @click.stop="uni.navigateTo({ url: `/pages/reports/edit?id=${r.id}` })">编辑</text>
      </view>
      <text class="arrow">›</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listReports } from '../../api'

const reports = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    reports.value = await listReports()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function openView(r) {
  uni.navigateTo({ url: `/pages/reports/view?id=${r.id}&name=${encodeURIComponent(r.name)}` })
}

onShow(load)
</script>

<style>
.page { padding: 24rpx; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.total { color: #909399; font-size: 26rpx; }
.add-btn { background: linear-gradient(135deg, #7c3aed, #a855f7); color: #fff; font-size: 28rpx; padding: 12rpx 32rpx; border-radius: 32rpx; }
.hint { text-align: center; color: #909399; padding: 80rpx 0; font-size: 28rpx; }
.card {
  background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05); position: relative;
}
.card-title { font-size: 32rpx; font-weight: 600; color: #303133; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 8rpx; }
.card-footer { display: flex; gap: 24rpx; border-top: 1rpx solid #f0f0f0; margin-top: 16rpx; padding-top: 16rpx; }
.foot-act { font-size: 26rpx; color: #409eff; }
.arrow { position: absolute; right: 28rpx; top: 40rpx; color: #c0c4cc; font-size: 40rpx; }
</style>
