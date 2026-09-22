<template>
  <view class="page">
    <view class="header">
      <view class="total">共 {{ tables.length }} 张表</view>
      <view class="add-btn" @click="uni.navigateTo({ url: '/pages/tables/create' })">+ 新建数据表</view>
    </view>
    <view v-if="loading" class="hint">加载中…</view>
    <view v-else-if="!tables.length" class="hint">还没有数据表，点右上角新建</view>
    <view
      v-for="t in tables" :key="t.id" class="card"
      @click="openRecords(t)"
      @longpress="del(t)"
    >
      <view class="card-title">{{ t.label }}</view>
      <view class="card-sub">{{ t.record_count ?? '-' }} 条记录</view>
      <text class="arrow">›</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listTables, deleteTable } from '../../api'

const tables = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    tables.value = await listTables()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function openRecords(t) {
  uni.navigateTo({ url: `/pages/records/list?table_id=${t.id}&label=${encodeURIComponent(t.label)}` })
}

function del(t) {
  uni.showModal({
    title: '确认删除',
    content: `删除数据表「${t.label}」及其全部记录？此操作不可恢复`,
    confirmColor: '#f56c6c',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteTable(t.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        load()
      } catch (e) {
        uni.showToast({ title: e.message, icon: 'none' })
      }
    },
  })
}

onShow(load)
</script>

<style>
.page { padding: 24rpx; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.total { color: #909399; font-size: 26rpx; }
.add-btn { background: #409eff; color: #fff; font-size: 28rpx; padding: 12rpx 32rpx; border-radius: 32rpx; }
.hint { text-align: center; color: #909399; padding: 80rpx 0; font-size: 28rpx; }
.card {
  background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05); position: relative;
}
.card-title { font-size: 32rpx; font-weight: 600; color: #303133; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 8rpx; }
.arrow { position: absolute; right: 28rpx; top: 50%; transform: translateY(-50%); color: #c0c4cc; font-size: 40rpx; }
</style>
