<template>
  <view class="page">
    <view class="header">
      <view class="total">共 {{ tasks.length }} 个任务</view>
      <view class="add-btn" @click="uni.navigateTo({ url: '/pages/tasks/edit' })">+ 新建任务</view>
    </view>
    <view v-if="loading" class="hint">加载中…</view>
    <view v-else-if="!tasks.length" class="hint">还没有任务，请先在电脑端创建</view>

    <view v-for="t in tasks" :key="t.id" class="card">
      <view class="card-head">
        <view class="card-title">{{ t.name }}</view>
        <switch :checked="t.enabled" @change="toggle(t)" color="#409eff" style="transform: scale(.8)" />
      </view>
      <view class="card-sub">{{ t.table_label }} · {{ scheduleDesc(t.schedule) }}</view>
      <view class="card-sub">
        {{ t.condition_mode === 'llm' ? 'LLM 判断' : conditionSummary(t) }} · {{ ACTION_LABELS[t.action?.type] || t.action?.type }}
      </view>
      <view v-if="t.last_run" class="card-sub">
        上次：{{ t.last_run.run_at }} 命中 {{ t.last_run.matched }} / 触发 {{ t.last_run.sent }}
        <text v-if="t.last_run.error" style="color: #f56c6c"> · {{ t.last_run.error }}</text>
      </view>
      <view class="actions">
        <view class="btn" :class="{ disabled: acting === t.id }" @click="test(t)">试运行</view>
        <view class="btn primary" :class="{ disabled: acting === t.id }" @click="run(t)">立即执行</view>
        <view class="btn" @click="uni.navigateTo({ url: `/pages/tasks/edit?id=${t.id}` })">编辑</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listTasks, runTask, testTask, toggleTask } from '../../api'

const ACTION_LABELS = { notify: '站内通知', email: '邮件', sms: '短信', webhook: 'Webhook' }
const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']
const OP_LABELS = {
  eq: '等于', ne: '不等于', gt: '大于', gte: '至少', lt: '小于', lte: '至多',
  contains: '包含', startswith: '开头是', in: '属于', null: '为空', not_null: '不为空',
  today: '当天', past_days: '过去 N 天', older_than_days: '早于 N 天前', within_days: '未来 N 天内',
}

const tasks = ref([])
const loading = ref(false)
const acting = ref(null)

async function load() {
  loading.value = true
  try {
    tasks.value = await listTasks()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function scheduleDesc(s) {
  if (s?.type === 'interval') return `每 ${s.minutes} 分钟`
  if (s?.type === 'cron') return `cron ${s.expr}`
  return '-'
}

function conditionSummary(t) {
  const rules = t.condition?.rules || []
  if (!rules.length) return '无条件'
  const logic = t.condition.logic === 'OR' ? ' 或 ' : ' 且 '
  return rules.map((r) => {
    const op = OP_LABELS[r.op] || r.op
    const val = NO_VALUE_OPS.includes(r.op) ? '' : ` ${r.value}${DAY_OPS.includes(r.op) ? ' 天' : ''}`
    return `${r.field} ${op}${val}`
  }).join(logic)
}

async function toggle(t) {
  try {
    await toggleTask(t.id)
    t.enabled = !t.enabled
    uni.showToast({ title: t.enabled ? '已启用' : '已停用', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function test(t) {
  acting.value = t.id
  uni.showLoading({ title: '求值中…' })
  try {
    const res = await testTask(t.id)
    uni.showModal({
      title: '试运行结果',
      content: `命中 ${res.matched} 条记录，其中 ${res.would_fire} 条会实际触发（其余在冷却期内）`,
      showCancel: false,
    })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
    acting.value = null
  }
}

async function run(t) {
  acting.value = t.id
  uni.showLoading({ title: '执行中…' })
  try {
    const res = await runTask(t.id)
    if (res.error) {
      uni.showModal({ title: '执行出错', content: res.error, showCancel: false })
    } else {
      uni.showToast({ title: `命中 ${res.matched}，触发 ${res.fired}`, icon: 'none' })
    }
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
    acting.value = null
  }
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
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05);
}
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 32rpx; font-weight: 600; color: #303133; flex: 1; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 10rpx; }
.actions { display: flex; gap: 16rpx; margin-top: 20rpx; border-top: 1rpx solid #f0f0f0; padding-top: 20rpx; }
.btn {
  font-size: 26rpx; color: #409eff; border: 1rpx solid #b3d8ff; border-radius: 32rpx;
  padding: 10rpx 32rpx;
}
.btn.primary { background: #409eff; color: #fff; border-color: #409eff; }
.btn.disabled { opacity: .5; }
</style>
