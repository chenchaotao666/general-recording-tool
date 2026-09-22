<template>
  <view class="page">
    <view v-if="loading" class="hint">加载中…</view>
    <template v-else>
      <!-- 智能识别 -->
      <view class="ai-btn" @click="recognize">
        <text class="ai-icon">📷</text>
        <text>{{ recognizing ? '识别中…' : '拍照 / 相册智能识别' }}</text>
      </view>
      <view v-if="visionResult" class="vision-panel">
        <view class="vp-title">识别结果（点击选择要填入的字段）</view>
        <view
          v-for="item in visionResult.items" :key="item.field"
          class="vp-row" @click="item.checked = !item.checked"
        >
          <text class="vp-check">{{ item.checked ? '✅' : '⬜' }}</text>
          <view class="vp-body">
            <text class="vp-label">{{ item.label }}</text>
            <text class="vp-value" :class="{ conflict: item.conflict }">{{ item.value }}</text>
            <text v-if="item.conflict" class="vp-conflict">⚠ {{ item.conflict }}</text>
          </view>
        </view>
        <view v-if="visionResult.notes" class="vp-notes">{{ visionResult.notes }}</view>
        <view class="vp-actions">
          <view class="vp-btn cancel" @click="visionResult = null">取消</view>
          <view class="vp-btn apply" @click="applyVision">填入所选字段</view>
        </view>
      </view>

      <view v-for="f in fields" :key="f.field_name" class="form-item">
        <view class="label">
          {{ f.label }}
          <text v-if="!f.nullable" class="required">*</text>
        </view>

        <!-- 下拉选择 -->
        <picker
          v-if="f.widget === 'select'"
          :range="optionsOf(f)" range-key="label"
          @change="(e) => onSelectChange(f, e)"
        >
          <view class="picker-value" :class="{ placeholder: form[f.field_name] === null || form[f.field_name] === '' }">
            {{ selectedLabel(f) || '请选择' }}
          </view>
        </picker>

        <!-- 开关 -->
        <switch v-else-if="f.widget === 'switch'" :checked="!!form[f.field_name]" @change="(e) => (form[f.field_name] = e.detail.value)" />

        <!-- 日期 -->
        <picker
          v-else-if="f.widget === 'date-picker'" mode="date"
          :value="form[f.field_name] || ''"
          @change="(e) => (form[f.field_name] = e.detail.value)"
        >
          <view class="picker-value" :class="{ placeholder: !form[f.field_name] }">{{ form[f.field_name] || '请选择日期' }}</view>
        </picker>

        <!-- 日期时间 -->
        <view v-else-if="f.widget === 'datetime-picker'" class="datetime-row">
          <picker mode="date" :value="datePart(f)" @change="(e) => setDatetime(f, e.detail.value, timePart(f))" class="dt-picker">
            <view class="picker-value" :class="{ placeholder: !datePart(f) }">{{ datePart(f) || '日期' }}</view>
          </picker>
          <picker mode="time" :value="timePart(f)" @change="(e) => setDatetime(f, datePart(f), e.detail.value)" class="dt-picker">
            <view class="picker-value" :class="{ placeholder: !timePart(f) }">{{ timePart(f) || '时间' }}</view>
          </picker>
        </view>

        <!-- 多行文本 -->
        <textarea
          v-else-if="f.widget === 'textarea'"
          v-model="form[f.field_name]" :placeholder="`请输入${f.label}`" class="textarea"
        />

        <!-- 数字 -->
        <input
          v-else-if="f.widget === 'number'"
          v-model="form[f.field_name]" type="digit" :placeholder="`请输入${f.label}`" class="input"
        />

        <!-- 默认单行输入 -->
        <input
          v-else
          v-model="form[f.field_name]" :placeholder="`请输入${f.label}`" class="input"
        />
      </view>

      <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { adoptVision, createRecord, getRecord, getTable, recognizeVision, updateRecord } from '../../api'

const tableId = ref(null)
const recordId = ref(null)
const fields = ref([])
const form = ref({})
const loading = ref(true)
const saving = ref(false)

onLoad(async (q) => {
  tableId.value = Number(q.table_id)
  recordId.value = q.record_id ? Number(q.record_id) : null
  uni.setNavigationBarTitle({ title: recordId.value ? '编辑记录' : '新增记录' })
  try {
    const t = await getTable(tableId.value)
    fields.value = [...t.fields].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
    const init = {}
    for (const f of fields.value) {
      init[f.field_name] = f.widget === 'switch' ? false : (f.default_value ?? (f.widget === 'number' ? null : ''))
    }
    if (recordId.value) {
      const rec = await getRecord(tableId.value, recordId.value)
      for (const f of fields.value) {
        const v = rec[f.field_name]
        init[f.field_name] = v === null || v === undefined ? init[f.field_name] : v
      }
    }
    form.value = init
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  } finally {
    loading.value = false
  }
})

function optionsOf(f) {
  return (f.options?.options || []).map((o) => (typeof o === 'object' ? { label: o.label ?? o.value, value: o.value } : { label: o, value: o }))
}

function selectedLabel(f) {
  const hit = optionsOf(f).find((o) => o.value === form.value[f.field_name])
  return hit ? hit.label : ''
}

function onSelectChange(f, e) {
  form.value[f.field_name] = optionsOf(f)[Number(e.detail.value)]?.value ?? null
}

function datePart(f) {
  return (form.value[f.field_name] || '').slice(0, 10)
}

function timePart(f) {
  return (form.value[f.field_name] || '').slice(11, 16)
}

function setDatetime(f, d, t) {
  if (!d && !t) return
  form.value[f.field_name] = `${d || ''} ${t || '00:00'}`.trim()
}

// ---------- 智能识别 ----------

const recognizing = ref(false)
const visionResult = ref(null)

function recognize() {
  if (recognizing.value) return
  uni.chooseImage({
    count: 3,
    sourceType: ['camera', 'album'],
    success: async (res) => {
      recognizing.value = true
      uni.showLoading({ title: '识别中…', mask: true })
      try {
        const data = await recognizeVision(
          tableId.value, res.tempFilePaths, form.value, recordId.value
        )
        const conflictMap = {}
        for (const c of data.conflicts || []) conflictMap[c.field_name] = c.reason
        const items = Object.entries(data.fields || {}).map(([field, value]) => {
          const f = fields.value.find((x) => x.field_name === field)
          return { field, label: f?.label || field, value, checked: true, conflict: conflictMap[field] || '' }
        })
        if (!items.length) {
          uni.showToast({ title: data.notes || '没有识别到可用字段', icon: 'none' })
          return
        }
        visionResult.value = { logId: data.log_id, items, notes: data.notes || '' }
      } catch (e) {
        uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
      } finally {
        uni.hideLoading()
        recognizing.value = false
      }
    },
  })
}

function applyVision() {
  const adopted = []
  for (const item of visionResult.value.items) {
    if (!item.checked) continue
    form.value[item.field] = item.value
    adopted.push(item.field)
  }
  if (visionResult.value.logId) adoptVision(visionResult.value.logId, adopted).catch(() => {})
  visionResult.value = null
  uni.showToast({ title: `已填入 ${adopted.length} 个字段`, icon: 'none' })
}

async function save() {
  // 必填校验
  for (const f of fields.value) {
    const v = form.value[f.field_name]
    if (!f.nullable && (v === null || v === undefined || v === '')) {
      uni.showToast({ title: `请填写${f.label}`, icon: 'none' })
      return
    }
  }
  const payload = {}
  for (const f of fields.value) {
    let v = form.value[f.field_name]
    if (v === '') v = null
    if (f.widget === 'number' && v !== null) v = Number(v)
    payload[f.field_name] = v
  }
  saving.value = true
  try {
    if (recordId.value) {
      await updateRecord(tableId.value, recordId.value, payload)
    } else {
      await createRecord(tableId.value, payload)
    }
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 600)
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    saving.value = false
  }
}
</script>

<style>
.page { padding: 24rpx; padding-bottom: 60rpx; }
.hint { text-align: center; color: #909399; padding: 80rpx 0; font-size: 28rpx; }
.form-item { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.label { font-size: 26rpx; color: #606266; margin-bottom: 12rpx; }
.required { color: #f56c6c; margin-left: 4rpx; }
.input { font-size: 30rpx; color: #303133; }
.textarea { font-size: 30rpx; color: #303133; width: 100%; min-height: 120rpx; }
.picker-value { font-size: 30rpx; color: #303133; padding: 8rpx 0; }
.placeholder { color: #c0c4cc; }
.datetime-row { display: flex; gap: 24rpx; }
.dt-picker { flex: 1; }
.save-btn {
  margin-top: 32rpx; background: #409eff; color: #fff; border-radius: 48rpx; font-size: 32rpx;
}
.save-btn[disabled] { background: #a0cfff; }
.ai-btn {
  background: linear-gradient(135deg, #7c3aed, #a855f7); color: #fff; border-radius: 16rpx;
  padding: 24rpx; margin-bottom: 20rpx; display: flex; align-items: center; justify-content: center;
  font-size: 30rpx;
}
.ai-icon { margin-right: 12rpx; }
.vision-panel { background: #faf5ff; border: 1rpx solid #e9d5ff; border-radius: 16rpx; padding: 24rpx; margin-bottom: 20rpx; }
.vp-title { font-size: 26rpx; font-weight: 600; color: #7c3aed; margin-bottom: 16rpx; }
.vp-row { display: flex; align-items: flex-start; padding: 10rpx 0; }
.vp-check { margin-right: 12rpx; font-size: 28rpx; }
.vp-body { flex: 1; display: flex; flex-direction: column; }
.vp-label { font-size: 24rpx; color: #909399; }
.vp-value { font-size: 28rpx; color: #303133; word-break: break-all; }
.vp-value.conflict { color: #e6a23c; }
.vp-conflict { font-size: 22rpx; color: #e6a23c; }
.vp-notes { font-size: 22rpx; color: #909399; margin-top: 12rpx; }
.vp-actions { display: flex; gap: 16rpx; margin-top: 20rpx; }
.vp-btn { flex: 1; text-align: center; font-size: 28rpx; padding: 14rpx 0; border-radius: 32rpx; }
.vp-btn.cancel { color: #909399; border: 1rpx solid #dcdfe6; background: #fff; }
.vp-btn.apply { background: #7c3aed; color: #fff; }
</style>
