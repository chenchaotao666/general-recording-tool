<template>
  <view class="page">
    <view class="header">
      <view class="total">{{ notifications.filter((n) => !n.read).length }} 条未读</view>
      <view class="read-all" @click="readAll">全部已读</view>
    </view>
    <view v-if="loading" class="hint">加载中…</view>
    <view v-else-if="!notifications.length" class="hint">暂无通知</view>
    <view
      v-for="n in notifications" :key="n.id" class="card" :class="{ unread: !n.read }"
      @click="open(n)"
    >
      <view class="card-title">
        <text v-if="!n.read" class="dot" />{{ n.title }}
      </view>
      <view class="card-content">{{ n.content }}</view>
      <view class="card-time">{{ (n.created_at || '').slice(0, 16) }}</view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listNotifications, markRead } from '../../api'

const notifications = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    notifications.value = await listNotifications()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function open(n) {
  if (!n.read) {
    await markRead({ ids: [n.id] }).catch(() => {})
    n.read = true
  }
  if (n.link) {
    // 通知链接形如 /t/{table_id}，跳到记录列表
    const m = n.link.match(/^\/t\/(\d+)/)
    if (m) uni.navigateTo({ url: `/pages/records/list?table_id=${m[1]}` })
  }
}

async function readAll() {
  await markRead({ all: true }).catch(() => {})
  notifications.value.forEach((n) => { n.read = true })
}

onShow(load)
</script>

<style>
.page { padding: 24rpx; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.total { color: #909399; font-size: 26rpx; }
.read-all { color: #409eff; font-size: 26rpx; padding: 8rpx 16rpx; }
.hint { text-align: center; color: #909399; padding: 80rpx 0; font-size: 28rpx; }
.card {
  background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05);
}
.card.unread { border-left: 6rpx solid #409eff; }
.card-title { font-size: 30rpx; font-weight: 600; color: #303133; }
.dot {
  display: inline-block; width: 14rpx; height: 14rpx; border-radius: 50%;
  background: #f56c6c; margin-right: 10rpx;
}
.card-content { font-size: 26rpx; color: #606266; margin-top: 10rpx; line-height: 1.6; }
.card-time { font-size: 22rpx; color: #c0c4cc; margin-top: 10rpx; }
</style>
