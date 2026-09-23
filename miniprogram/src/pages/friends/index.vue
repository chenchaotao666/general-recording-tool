<template>
  <view class="page">
    <!-- 添加好友 -->
    <view class="form-item">
      <view class="label">添加好友（搜索用户名发送申请，对方接受后成为好友）</view>
      <view class="search-row">
        <input v-model="keyword" class="input" placeholder="搜索用户名" confirm-type="search" @confirm="search" />
        <text class="act primary" @click="search">搜索</text>
      </view>
      <view v-for="u in results" :key="u.id" class="result-row">
        <text class="result-name">{{ u.username }}</text>
        <text class="act primary" @click="addFriend(u)">申请</text>
      </view>
      <view v-if="searched && !results.length" class="hint-inline">没有匹配的用户</view>
    </view>

    <!-- 收到的申请 -->
    <view class="sec-title">收到的申请（{{ requests.length }}）</view>
    <view v-for="r in requests" :key="r.id" class="card">
      <view class="card-head">
        <view class="card-title">{{ r.username }}</view>
        <view>
          <text class="act primary" @click="respond(r, 'accept')">接受</text>
          <text class="act danger" @click="respond(r, 'reject')">拒绝</text>
        </view>
      </view>
      <view class="card-sub">{{ r.created_at }}</view>
    </view>
    <view v-if="!requests.length" class="hint">暂无待处理的申请</view>

    <!-- 我的好友 -->
    <view class="sec-title">我的好友（{{ friends.length }}）</view>
    <view v-for="f in friends" :key="f.id" class="card">
      <view class="card-head">
        <view class="card-title">{{ f.username }}</view>
        <text class="del" @click="removeFriend(f)">删除</text>
      </view>
      <view class="card-sub">{{ f.since || '' }}</view>
    </view>
    <view v-if="!friends.length" class="hint">还没有好友</view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  acceptFriend, deleteFriend, listFriendRequests, listFriends,
  rejectFriend, requestFriend, searchUsers,
} from '../../api'

const keyword = ref('')
const results = ref([])
const searched = ref(false)
const friends = ref([])
const requests = ref([])

onShow(load)

async function load() {
  try {
    [friends.value, requests.value] = await Promise.all([listFriends(), listFriendRequests()])
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function search() {
  searched.value = true
  try {
    results.value = await searchUsers(keyword.value.trim(), 'all')
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function addFriend(u) {
  try {
    const r = await requestFriend(u.username)
    uni.showToast({ title: r.status === 'accepted' ? '已自动成为好友' : '申请已发送', icon: 'none' })
    results.value = results.value.filter(x => x.id !== u.id)
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function respond(r, action) {
  try {
    await (action === 'accept' ? acceptFriend(r.id) : rejectFriend(r.id))
    uni.showToast({ title: action === 'accept' ? '已接受' : '已拒绝', icon: 'success' })
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

function removeFriend(f) {
  uni.showModal({
    title: '删除好友',
    content: `删除好友 ${f.username}？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteFriend(f.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        load()
      } catch (e) {
        uni.showToast({ title: e.message, icon: 'none' })
      }
    },
  })
}
</script>

<style>
.page { padding: 24rpx; padding-bottom: 60rpx; }
.form-item { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.label { font-size: 26rpx; color: #606266; margin-bottom: 12rpx; }
.search-row { display: flex; align-items: center; gap: 16rpx; }
.input { flex: 1; font-size: 30rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 12rpx; padding: 16rpx 20rpx; }
.act { font-size: 28rpx; color: #606266; padding: 8rpx 12rpx; }
.act.primary { color: #409eff; }
.act.danger { color: #f56c6c; }
.result-row { display: flex; justify-content: space-between; align-items: center; padding: 14rpx 0; border-top: 1rpx solid #f5f5f5; }
.result-row:first-of-type { margin-top: 12rpx; }
.result-name { font-size: 30rpx; color: #303133; }
.hint-inline { font-size: 24rpx; color: #c0c4cc; padding: 16rpx 0 4rpx; }
.sec-title { font-size: 26rpx; color: #909399; margin: 16rpx 0 12rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 30rpx; font-weight: 600; color: #303133; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 8rpx; }
.del { font-size: 26rpx; color: #f56c6c; padding: 4rpx 12rpx; }
.hint { text-align: center; color: #c0c4cc; font-size: 26rpx; padding: 30rpx 0; }
</style>
