<template>
  <view class="page">
    <view class="mode-tabs">
      <view class="mode-tab" :class="{ active: mode === 'manual' }" @click="mode = 'manual'">手动建表</view>
      <view class="mode-tab" :class="{ active: mode === 'excel' }" @click="mode = 'excel'">Excel 导入</view>
    </view>

    <view class="form-item">
      <view class="label">表名称 <text class="required">*</text></view>
      <input v-model="label" class="input" placeholder="如：客户跟进记录" />
    </view>

    <!-- Excel 导入流程 -->
    <template v-if="mode === 'excel'">
      <view class="form-item">
        <view class="label">Excel 文件（.xlsx / .csv）</view>
        <view class="file-btn" @click="chooseFile">{{ fileName || '从聊天文件中选择' }}</view>
      </view>
      <template v-if="uploaded">
        <view class="form-item">
          <view class="label">工作表</view>
          <picker :range="uploaded.sheets" range-key="name" @change="onSheetChange">
            <view class="picker-value">{{ uploaded.sheets[sheetIndex].name }}</view>
          </picker>
        </view>
        <view class="form-item">
          <view class="label">表头在第几行</view>
          <input v-model="headerRow" type="number" class="input" />
        </view>
        <button class="gen-btn" :disabled="analyzing" @click="analyze">{{ analyzing ? 'AI 分析中…' : 'AI 分析表结构' }}</button>
      </template>
    </template>

    <!-- 字段编辑（手动模式可直接编辑；导入模式由 AI 预填） -->
    <template v-if="mode === 'manual' || analyzed">
      <view class="sec-title">字段（{{ fields.length }}）</view>
      <view v-for="(f, i) in fields" :key="i" class="field-card">
        <view class="fc-head">
          <input v-model="f.label" class="fc-label" placeholder="字段显示名" />
          <text class="fc-del" @click="fields.splice(i, 1)">删除</text>
        </view>
        <view class="fc-row">
          <input v-model="f.field_name" class="fc-input" placeholder="英文名 snake_case" />
          <picker :range="DATA_TYPES" :value="DATA_TYPES.indexOf(f.data_type)" @change="(e) => (f.data_type = DATA_TYPES[Number(e.detail.value)])">
            <view class="fc-picker">{{ f.data_type }} ›</view>
          </picker>
        </view>
        <view class="fc-row">
          <picker :range="WIDGET_LABELS" :value="WIDGETS.indexOf(f.widget)" @change="(e) => (f.widget = WIDGETS[Number(e.detail.value)])">
            <view class="fc-picker">{{ WIDGET_LABELS[WIDGETS.indexOf(f.widget)] || f.widget }} ›</view>
          </picker>
          <view class="fc-nullable">
            <text>可空</text>
            <switch :checked="f.nullable" @change="(e) => (f.nullable = e.detail.value)" style="transform: scale(.7)" />
          </view>
        </view>
        <input
          v-if="f.widget === 'select'" v-model="f.optionsText" class="fc-input"
          placeholder="枚举选项，用逗号分隔"
        />
      </view>
      <view class="add-field" @click="addField">+ 添加字段</view>

      <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '创建中…' : (mode === 'excel' ? '创建并导入' : '创建数据表') }}</button>
    </template>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { analyzeExcel, createTable, uploadExcelFile } from '../../api'

const DATA_TYPES = ['varchar', 'text', 'int', 'decimal', 'date', 'datetime', 'bool']
const WIDGETS = ['input', 'textarea', 'number', 'date-picker', 'datetime-picker', 'select', 'switch']
const WIDGET_LABELS = ['单行文本', '多行文本', '数字', '日期', '日期时间', '下拉选择', '开关']

const mode = ref('manual')
const label = ref('')
const fields = ref([])
const saving = ref(false)

// Excel 导入状态
const fileName = ref('')
const uploaded = ref(null)
const sheetIndex = ref(0)
const headerRow = ref('1')
const analyzing = ref(false)
const analyzed = ref(false)

function addField() {
  fields.value.push({
    source_header: '', field_name: '', label: '', data_type: 'varchar',
    length: 255, nullable: true, default_value: null, widget: 'input', optionsText: '',
  })
}

// 手动模式默认给 3 个空字段
if (mode.value === 'manual' && !fields.value.length) {
  addField(); addField(); addField()
}

function chooseFile() {
  uni.chooseMessageFile({
    count: 1,
    type: 'file',
    extension: ['xlsx', 'csv'],
    success: async (res) => {
      const f = res.tempFiles[0]
      fileName.value = f.name
      uni.showLoading({ title: '上传中…', mask: true })
      try {
        uploaded.value = await uploadExcelFile(f.path, f.name)
        sheetIndex.value = 0
        analyzed.value = false
        // 后端已探测过表头行，直接预填
        headerRow.value = String(uploaded.value.sheets[0]?.header_row || 1)
        if (!label.value) label.value = f.name.replace(/\.(xlsx|csv)$/i, '')
      } catch (e) {
        uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
      } finally {
        uni.hideLoading()
      }
    },
  })
}

function onSheetChange(e) {
  sheetIndex.value = Number(e.detail.value)
  analyzed.value = false
  headerRow.value = String(uploaded.value.sheets[sheetIndex.value]?.header_row || 1)
}

async function analyze() {
  analyzing.value = true
  uni.showLoading({ title: 'AI 分析中…', mask: true })
  try {
    const res = await analyzeExcel({
      file_id: uploaded.value.file_id,
      sheet_name: uploaded.value.sheets[sheetIndex.value].name,
      header_row: Number(headerRow.value) || 1,
    })
    fields.value = (res.columns || []).map((c) => ({
      source_header: c.source_header, field_name: c.field_name, label: c.label,
      data_type: c.data_type, length: c.length || 255, nullable: c.nullable !== false,
      default_value: c.default_value ?? null, widget: c.widget,
      optionsText: ((c.options?.options) || []).map((o) => (typeof o === 'object' ? o.value : o)).join(','),
    }))
    analyzed.value = true
    if (res.notes) uni.showToast({ title: res.notes.slice(0, 40), icon: 'none', duration: 3000 })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
    analyzing.value = false
  }
}

async function save() {
  if (!label.value.trim()) return uni.showToast({ title: '请填写表名称', icon: 'none' })
  const valid = fields.value.filter((f) => f.field_name && f.label)
  if (!valid.length) return uni.showToast({ title: '至少需要一个完整字段（英文名+显示名）', icon: 'none' })
  const payload = {
    label: label.value.trim(),
    fields: valid.map((f) => ({
      source_header: f.source_header || f.label,
      field_name: f.field_name.trim(),
      label: f.label.trim(),
      data_type: f.data_type,
      length: f.length || 255,
      nullable: f.nullable,
      default_value: f.default_value,
      widget: f.widget,
      options: f.widget === 'select'
        ? { options: f.optionsText.split(',').map((s) => s.trim()).filter(Boolean) }
        : {},
    })),
  }
  if (mode.value === 'excel' && uploaded.value) {
    payload.source = {
      file_id: uploaded.value.file_id,
      sheet_name: uploaded.value.sheets[sheetIndex.value].name,
      header_row: Number(headerRow.value) || 1,
    }
  }
  saving.value = true
  try {
    const res = await createTable(payload)
    const imp = res.import_report
    uni.showModal({
      title: '创建成功',
      content: imp ? `导入 ${imp.total} 行：成功 ${imp.success}，失败 ${imp.failed}` : `数据表「${label.value}」已创建`,
      showCancel: false,
      success: () => uni.navigateBack(),
    })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    saving.value = false
  }
}
</script>

<style>
.page { padding: 24rpx; padding-bottom: 60rpx; }
.mode-tabs { display: flex; background: #fff; border-radius: 16rpx; padding: 8rpx; margin-bottom: 20rpx; }
.mode-tab { flex: 1; text-align: center; font-size: 28rpx; color: #606266; padding: 16rpx 0; border-radius: 12rpx; }
.mode-tab.active { background: #409eff; color: #fff; }
.form-item { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.label { font-size: 26rpx; color: #606266; margin-bottom: 12rpx; }
.required { color: #f56c6c; }
.input { font-size: 30rpx; color: #303133; }
.picker-value { font-size: 30rpx; color: #303133; padding: 8rpx 0; }
.file-btn { font-size: 28rpx; color: #409eff; border: 1rpx dashed #b3d8ff; border-radius: 12rpx; padding: 24rpx; text-align: center; }
.gen-btn { background: linear-gradient(135deg, #7c3aed, #a855f7); color: #fff; border-radius: 48rpx; font-size: 30rpx; margin: 4rpx 0 20rpx; }
.gen-btn[disabled] { opacity: .5; }
.sec-title { font-size: 26rpx; color: #909399; margin: 8rpx 0 12rpx; }
.field-card { background: #fff; border-radius: 16rpx; padding: 20rpx 24rpx; margin-bottom: 12rpx; }
.fc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12rpx; }
.fc-label { font-size: 30rpx; font-weight: 600; color: #303133; flex: 1; }
.fc-del { font-size: 24rpx; color: #f56c6c; padding: 4rpx 12rpx; }
.fc-row { display: flex; gap: 16rpx; align-items: center; margin-bottom: 12rpx; }
.fc-input { flex: 1; font-size: 26rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 8rpx; padding: 10rpx 16rpx; }
.fc-picker { font-size: 26rpx; color: #409eff; border: 1rpx solid #b3d8ff; border-radius: 8rpx; padding: 10rpx 20rpx; }
.fc-nullable { display: flex; align-items: center; font-size: 26rpx; color: #606266; }
.add-field { text-align: center; color: #409eff; font-size: 28rpx; border: 1rpx dashed #b3d8ff; border-radius: 12rpx; padding: 20rpx; margin-bottom: 24rpx; }
.save-btn { background: #409eff; color: #fff; border-radius: 48rpx; font-size: 32rpx; }
.save-btn[disabled] { background: #a0cfff; }
</style>
