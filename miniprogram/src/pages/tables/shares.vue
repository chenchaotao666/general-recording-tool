<template>
  <view class="page">
    <view class="form-item">
      <view class="label">添加/更新分享（只能分享给好友或同组用户）</view>
      <view class="search-row">
        <input v-model="keyword" class="input" placeholder="搜索好友/同组用户" confirm-type="search" @confirm="search" />
        <text class="act primary" @click="search">搜索</text>
      </view>
      <view class="perm-row">
        <text
          v-for="u in options" :key="u.id"
          class="chip" :class="{ on: selected && selected.id === u.id }"
          @click="selected = u"
        >{{ u.username }}</text>
        <text v-if="!options.length" class="hint-inline">没有可分享的用户，先到「设置-好友」添加好友</text>
      </view>
      <view class="perm-row">
        <text
          v-for="p in PERMS" :key="p.key"
          class="chip" :class="{ on: form[p.key] }"
          @click="form[p.key] = !form[p.key]"
        >{{ p.label }}</text>
      </view>
      <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '添加 / 更新' }}</button>
      <view class="hint-line">直发分享需对方接受后生效；被拒绝后可在此重新发起</view>
    </view>

    <view class="sec-title">已分享（{{ shares.length }}）</view>
    <view v-for="s in shares" :key="s.id" class="card">
      <view class="card-head">
        <view class="card-title">
          {{ s.target }}
          <text v-if="s.target_type === 'group'" class="tag group">组</text>
          <text v-else-if="s.status === 'pending'" class="tag pending">待确认</text>
          <text v-else-if="s.status === 'rejected'" class="tag rejected">已拒绝</text>
        </view>
        <view>
          <text v-if="s.status === 'rejected'" class="act primary" @click="reShare(s)">重新发起</text>
          <text class="del" @click="remove(s)">移除</text>
        </view>
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
import { deleteShare, listFriends, listShares, putShare, searchUsers } from '../../api'

const PERMS = [
  { key: 'can_view', label: '查看' },
  { key: 'can_create', label: '新增' },
  { key: 'can_edit', label: '编辑' },
  { key: 'can_delete', label: '删除' },
]

const tableId = ref(null)
const label = ref('')
const shares = ref([])
const keyword = ref('')
const options = ref([])
const selected = ref(null)
const saving = ref(false)
const form = ref({ can_view: true, can_create: false, can_edit: false, can_delete: false })

onLoad((q) => {
  tableId.value = Number(q.table_id)
  label.value = q.label ? decodeURIComponent(q.label) : ''
  uni.setNavigationBarTitle({ title: `分享「${label.value}」` })
  load()
  loadFriends()
})

async function load() {
  try {
    shares.value = await listShares(tableId.value)
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function loadFriends() {
  try {
    options.value = await listFriends()
  } catch { /* 无好友时为空 */ }
}

async function search() {
  try {
    options.value = await searchUsers(keyword.value.trim(), 'shareable')
    if (!options.value.length) uni.showToast({ title: '没有匹配的好友/同组用户', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function save() {
  if (!selected.value) return uni.showToast({ title: '请先选择用户', icon: 'none' })
  saving.value = true
  try {
    await putShare(tableId.value, { user_id: selected.value.id, ...form.value })
    uni.showToast({ title: '已保存', icon: 'success' })
    selected.value = null
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    saving.value = false
  }
}

function reShare(s) {
  putShare(tableId.value, {
    username: s.target,
    can_view: s.can_view, can_create: s.can_create, can_edit: s.can_edit, can_delete: s.can_delete,
  }).then(() => {
    uni.showToast({ title: '已重新发起', icon: 'success' })
    load()
  }).catch((e) => uni.showToast({ title: e.message, icon: 'none' }))
}

function remove(s) {
  uni.showModal({
    title: '取消分享',
    content: `取消 ${s.target} 对「${label.value}」的访问？`,
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
.search-row { display: flex; align-items: center; gap: 16rpx; }
.input { flex: 1; font-size: 30rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 12rpx; padding: 16rpx 20rpx; }
.act { font-size: 28rpx; color: #606266; padding: 8rpx 12rpx; }
.act.primary { color: #409eff; }
.perm-row { display: flex; gap: 12rpx; flex-wrap: wrap; margin: 16rpx 0; }
.chip { font-size: 24rpx; color: #606266; background: #f5f7fa; border-radius: 8rpx; padding: 10rpx 24rpx; }
.chip.on { background: #409eff; color: #fff; }
.hint-inline { font-size: 24rpx; color: #c0c4cc; }
.hint-line { font-size: 22rpx; color: #c0c4cc; margin-top: 12rpx; }
.save-btn { background: #409eff; color: #fff; border-radius: 48rpx; font-size: 30rpx; }
.save-btn[disabled] { background: #a0cfff; }
.sec-title { font-size: 26rpx; color: #909399; margin: 8rpx 0 12rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 30rpx; font-weight: 600; color: #303133; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 8rpx; }
.tag { font-size: 20rpx; border-radius: 6rpx; padding: 4rpx 10rpx; margin-left: 10rpx; font-weight: normal; }
.tag.group { background: #fdf6ec; color: #e6a23c; }
.tag.pending { background: #fdf6ec; color: #e6a23c; }
.tag.rejected { background: #fef0f0; color: #f56c6c; }
.del { font-size: 26rpx; color: #f56c6c; padding: 4rpx 12rpx; }
.hint { text-align: center; color: #c0c4cc; font-size: 26rpx; padding: 40rpx 0; }
</style>
