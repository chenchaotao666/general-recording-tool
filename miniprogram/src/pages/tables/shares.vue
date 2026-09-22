<template>
  <view class="page">
    <view class="form-item">
      <view class="label">添加/更新分享</view>
      <input v-model="username" class="input" placeholder="对方用户名" />
      <view class="perm-row">
        <text
          v-for="p in PERMS" :key="p.key"
          class="chip" :class="{ on: form[p.key] }"
          @click="form[p.key] = !form[p.key]"
        >{{ p.label }}</text>
      </view>
      <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '添加 / 更新' }}</button>
    </view>

    <view class="sec-title">已分享（{{ shares.length }}）</view>
    <view v-for="s in shares" :key="s.id" class="card">
      <view class="card-head">
        <view class="card-title">{{ s.username }}</view>
        <text class="del" @click="remove(s)">移除</text>
      </view>
      <view class="card-sub">
        {{ s.can_view ? '查看' : '' }}{{ s.can_create ? ' 新增' : '' }}{{ s.can_edit ? ' 编辑' : '' }}{{ s.can_delete ? ' 删除' : '' }}
      </view>
    </view>
    <view v-if="!shares.length" class="hint">还没有分享给任何人</view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { deleteShare, listShares, putShare } from '../../api'

const PERMS = [
  { key: 'can_view', label: '查看' },
  { key: 'can_create', label: '新增' },
  { key: 'can_edit', label: '编辑' },
  { key: 'can_delete', label: '删除' },
]

const tableId = ref(null)
const label = ref('')
const shares = ref([])
const username = ref('')
const saving = ref(false)
const form = ref({ can_view: true, can_create: false, can_edit: false, can_delete: false })

onLoad((q) => {
  tableId.value = Number(q.table_id)
  label.value = q.label ? decodeURIComponent(q.label) : ''
  uni.setNavigationBarTitle({ title: `分享「${label.value}」` })
  load()
})

async function load() {
  try {
    shares.value = await listShares(tableId.value)
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function save() {
  if (!username.value.trim()) return uni.showToast({ title: '请输入用户名', icon: 'none' })
  saving.value = true
  try {
    await putShare(tableId.value, { username: username.value.trim(), ...form.value })
    uni.showToast({ title: '已保存', icon: 'success' })
    username.value = ''
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    saving.value = false
  }
}

function remove(s) {
  uni.showModal({
    title: '取消分享',
    content: `取消 ${s.username} 对「${label.value}」的访问？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteShare(tableId.value, s.id)
        uni.showToast({ title: '已移除', icon: 'success' })
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
.input { font-size: 30rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 12rpx; padding: 16rpx 20rpx; }
.perm-row { display: flex; gap: 12rpx; flex-wrap: wrap; margin: 16rpx 0; }
.chip { font-size: 24rpx; color: #606266; background: #f5f7fa; border-radius: 8rpx; padding: 10rpx 24rpx; }
.chip.on { background: #409eff; color: #fff; }
.save-btn { background: #409eff; color: #fff; border-radius: 48rpx; font-size: 30rpx; }
.save-btn[disabled] { background: #a0cfff; }
.sec-title { font-size: 26rpx; color: #909399; margin: 8rpx 0 12rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 30rpx; font-weight: 600; color: #303133; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 8rpx; }
.del { font-size: 26rpx; color: #f56c6c; padding: 4rpx 12rpx; }
.hint { text-align: center; color: #c0c4cc; font-size: 26rpx; padding: 40rpx 0; }
</style>
