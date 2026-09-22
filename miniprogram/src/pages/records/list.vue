<template>
  <view class="page">
    <view class="header">
      <view class="total">共 {{ total }} 条</view>
      <view class="add-btn" @click="openEdit(null)">+ 新增</view>
    </view>

    <view v-if="loading && !records.length" class="hint">加载中…</view>
    <view v-else-if="!records.length" class="hint">暂无记录，点右上角新增</view>

    <view v-for="r in records" :key="r.id" class="card" @click="openEdit(r)">
      <view v-for="f in displayFields" :key="f.field_name" class="row">
        <text class="row-label">{{ f.label }}</text>
        <text class="row-value">{{ displayValue(r, f) }}</text>
      </view>
      <view class="card-footer">
        <text class="time">#{{ r.id }} · {{ fmtTime(r.created_at) }}</text>
        <text class="del" @click.stop="del(r)">删除</text>
      </view>
    </view>

    <view v-if="records.length && records.length < total" class="more" @click="loadMore">
      {{ loading ? '加载中…' : '加载更多' }}
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { deleteRecord, getTable, listRecords } from '../../api'

const tableId = ref(null)
const fields = ref([])
const records = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const PAGE_SIZE = 20

// 列表最多展示前 6 个字段（按 sort_order）
const displayFields = computed(() =>
  [...fields.value].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)).slice(0, 6)
)

onLoad(async (q) => {
  tableId.value = Number(q.table_id)
  uni.setNavigationBarTitle({ title: q.label ? decodeURIComponent(q.label) : '记录' })
  const t = await getTable(tableId.value).catch((e) => {
    uni.showToast({ title: e.message, icon: 'none' })
    return null
  })
  if (t) fields.value = t.fields
})

onShow(() => {
  if (tableId.value) reload()
})

async function load(append) {
  loading.value = true
  try {
    const res = await listRecords(tableId.value, {
      page: page.value, page_size: PAGE_SIZE, sort_by: 'id', sort_order: 'desc',
    })
    records.value = append ? [...records.value, ...res.items] : res.items
    total.value = res.total
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load(false)
}

function loadMore() {
  if (loading.value) return
  page.value += 1
  load(true)
}

function displayValue(r, f) {
  const v = r[f.field_name]
  if (v === null || v === undefined || v === '') return '—'
  if (f.data_type === 'bool') return v ? '是' : '否'
  if (f.widget === 'select') {
    const opts = f.options?.options || []
    const hit = opts.find((o) => (typeof o === 'object' ? o.value : o) === v)
    return typeof hit === 'object' ? hit.label : (hit ?? v)
  }
  return String(v)
}

function fmtTime(t) {
  return (t || '').slice(0, 16)
}

function openEdit(r) {
  const rid = r ? r.id : ''
  uni.navigateTo({ url: `/pages/records/edit?table_id=${tableId.value}&record_id=${rid}` })
}

function del(r) {
  uni.showModal({
    title: '确认删除',
    content: `删除记录 #${r.id}？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteRecord(tableId.value, r.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        reload()
      } catch (e) {
        uni.showToast({ title: e.message, icon: 'none' })
      }
    },
  })
}
</script>

<style>
.page { padding: 24rpx; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.total { color: #909399; font-size: 26rpx; }
.add-btn {
  background: #409eff; color: #fff; font-size: 28rpx; padding: 12rpx 32rpx; border-radius: 32rpx;
}
.hint { text-align: center; color: #909399; padding: 80rpx 0; font-size: 28rpx; }
.card {
  background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 20rpx;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05);
}
.row { display: flex; padding: 6rpx 0; font-size: 28rpx; }
.row-label { color: #909399; width: 160rpx; flex-shrink: 0; }
.row-value { color: #303133; flex: 1; word-break: break-all; }
.card-footer {
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1rpx solid #f0f0f0; margin-top: 12rpx; padding-top: 12rpx;
}
.time { font-size: 22rpx; color: #c0c4cc; }
.del { font-size: 26rpx; color: #f56c6c; padding: 4rpx 12rpx; }
.more { text-align: center; color: #409eff; font-size: 28rpx; padding: 24rpx; }
</style>
