<template>
  <view class="page">
    <!-- AI 辅助 -->
    <view class="ai-box">
      <textarea v-model="aiDesc" class="ai-textarea" placeholder="AI 辅助：用自然语言描述任务，自动生成下方配置" />
      <view class="ai-btn" @click="aiGenerate">{{ aiGenerating ? 'AI 设计中…' : '✨ AI 生成' }}</view>
      <view v-if="aiNotes" class="ai-notes">{{ aiNotes }}</view>
    </view>

    <view class="form-item">
      <view class="label">任务名称 <text class="required">*</text></view>
      <input v-model="form.name" class="input" placeholder="如：超过30天未跟进提醒" />
    </view>

    <view class="form-item">
      <view class="label">数据表 <text class="required">*</text></view>
      <picker :range="tables" range-key="label" :value="tableIndex" @change="onTableChange">
        <view class="picker-value" :class="{ placeholder: tableIndex < 0 }">
          {{ tableIndex >= 0 ? tables[tableIndex].label : '请选择数据表' }}
        </view>
      </picker>
    </view>

    <view class="form-item">
      <view class="label">判断方式</view>
      <view class="radio-row">
        <view class="radio" :class="{ active: form.condition_mode === 'structured' }" @click="form.condition_mode = 'structured'">结构化条件</view>
        <view class="radio" :class="{ active: form.condition_mode === 'llm' }" @click="form.condition_mode = 'llm'">LLM 智能判断</view>
      </view>
    </view>

    <!-- 结构化条件 -->
    <view v-if="form.condition_mode === 'structured'" class="form-item">
      <view class="label">条件</view>
      <view class="radio-row" style="margin-bottom: 16rpx">
        <view class="radio sm" :class="{ active: form.condition.logic === 'AND' }" @click="form.condition.logic = 'AND'">满足全部</view>
        <view class="radio sm" :class="{ active: form.condition.logic === 'OR' }" @click="form.condition.logic = 'OR'">满足任一</view>
      </view>
      <view v-for="(r, i) in form.condition.rules" :key="i" class="cond-card">
        <view class="fc-row">
          <picker :range="fieldOptions" range-key="label" @change="(e) => onRuleField(r, e)">
            <view class="fc-picker wide">{{ fieldLabel(r.field) || '选择字段' }} ›</view>
          </picker>
          <picker :range="opsFor(r.field)" range-key="label" @change="(e) => (r.op = opsFor(r.field)[Number(e.detail.value)].value)">
            <view class="fc-picker">{{ opLabel(r) }} ›</view>
          </picker>
          <text class="fc-del" @click="form.condition.rules.splice(i, 1)">删</text>
        </view>
        <view v-if="!NO_VALUE_OPS.includes(r.op)" class="fc-row">
          <input
            v-if="DAY_OPS.includes(r.op)" v-model="r.value" type="number" class="fc-input" placeholder="天数"
          />
          <picker
            v-else-if="fieldOf(r.field)?.widget === 'select'"
            :range="selectOptions(fieldOf(r.field))"
            @change="(e) => (r.value = selectOptions(fieldOf(r.field))[Number(e.detail.value)])"
          >
            <view class="fc-picker wide">{{ r.value || '选择值' }} ›</view>
          </picker>
          <picker
            v-else-if="fieldOf(r.field)?.data_type === 'bool'"
            :range="['是', '否']"
            @change="(e) => (r.value = Number(e.detail.value) === 0)"
          >
            <view class="fc-picker wide">{{ r.value === true ? '是' : r.value === false ? '否' : '选择值' }} ›</view>
          </picker>
          <picker
            v-else-if="['date', 'datetime'].includes(fieldOf(r.field)?.data_type)" mode="date"
            :value="r.value || ''" @change="(e) => (r.value = e.detail.value)"
          >
            <view class="fc-picker wide">{{ r.value || '选择日期' }} ›</view>
          </picker>
          <input
            v-else-if="['int', 'decimal'].includes(fieldOf(r.field)?.data_type)"
            v-model="r.value" type="digit" class="fc-input" placeholder="数值"
          />
          <input v-else v-model="r.value" class="fc-input" placeholder="值" />
        </view>
      </view>
      <view class="add-field" @click="form.condition.rules.push({ field: '', op: 'eq', value: null })">+ 添加条件</view>
    </view>

    <!-- LLM 判断 -->
    <view v-else class="form-item">
      <view class="label">条件描述 <text class="required">*</text></view>
      <textarea v-model="form.condition.description" class="textarea" placeholder="用自然语言描述判断条件" />
    </view>

    <view class="form-item">
      <view class="label">执行周期 <text class="required">*</text></view>
      <view class="radio-row" style="margin-bottom: 16rpx">
        <view class="radio sm" :class="{ active: form.schedule.type === 'interval' }" @click="form.schedule.type = 'interval'">每隔 N 分钟</view>
        <view class="radio sm" :class="{ active: form.schedule.type === 'cron' }" @click="form.schedule.type = 'cron'">cron 表达式</view>
      </view>
      <input v-if="form.schedule.type === 'interval'" v-model="form.schedule.minutes" type="number" class="fc-input" placeholder="分钟数，如 60" />
      <template v-else>
        <input v-model="form.schedule.expr" class="fc-input" placeholder="分 时 日 月 周，如 0 9 * * *" />
        <view class="preset-row">
          <text v-for="p in CRON_PRESETS" :key="p.expr" class="preset" @click="form.schedule.expr = p.expr">{{ p.label }}</text>
        </view>
      </template>
    </view>

    <view class="form-item">
      <view class="label">动作 <text class="required">*</text></view>
      <view class="radio-row" style="margin-bottom: 12rpx">
        <view v-for="[v, l] in ACTION_TYPES" :key="v" class="radio sm" :class="{ active: form.action.type === v }" @click="form.action.type = v">{{ l }}</view>
      </view>
      <view class="hint-text">邮件/短信每次执行只发一条汇总；通知/Webhook 逐条触发</view>
      <input
        v-if="form.action.type === 'webhook'" v-model="form.action.webhook_url" class="fc-input"
        placeholder="https://..." style="margin-top: 16rpx"
      />
    </view>

    <view class="form-item">
      <view class="label">内容模板 <text class="required">*</text>（点字段插入占位符）</view>
      <textarea v-model="form.action.template" class="textarea" placeholder="如：客户【{customer_name}】已超期未跟进" />
      <view class="chip-row">
        <text v-for="f in tableFields" :key="f.field_name" class="chip" @click="form.action.template += `{${f.field_name}}`">{{ f.label }}</text>
      </view>
    </view>

    <view v-if="['email', 'sms'].includes(form.action.type)" class="form-item">
      <view class="label">接收人</view>
      <view class="radio-row" style="margin-bottom: 16rpx">
        <view class="radio sm" :class="{ active: form.action.recipients.type === 'fixed' }" @click="form.action.recipients.type = 'fixed'">固定地址</view>
        <view class="radio sm" :class="{ active: form.action.recipients.type === 'field' }" @click="form.action.recipients.type = 'field'">取自字段</view>
      </view>
      <input
        v-if="form.action.recipients.type === 'fixed'"
        v-model="form.action.recipients.value" class="fc-input"
        :placeholder="form.action.type === 'email' ? '邮箱，多个用逗号分隔' : '手机号，多个用逗号分隔'"
      />
      <picker v-else :range="tableFields" range-key="label" @change="(e) => (form.action.recipients.field = tableFields[Number(e.detail.value)].field_name)">
        <view class="fc-picker wide">{{ fieldLabel(form.action.recipients.field) || '选择字段' }} ›</view>
      </picker>
    </view>

    <view class="form-item">
      <view class="label">高级设置</view>
      <view class="fc-row">
        <text class="lbl">冷却期(小时)</text>
        <input v-model="form.cooldown_hours" type="number" class="fc-input" />
      </view>
      <view class="fc-row">
        <text class="lbl">单次上限(条)</text>
        <input v-model="form.max_per_run" type="number" class="fc-input" />
      </view>
      <view class="fc-row">
        <text class="lbl">启用</text>
        <switch :checked="form.enabled" @change="(e) => (form.enabled = e.detail.value)" />
      </view>
    </view>

    <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存任务' }}</button>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { aiAssistTask, createTask, getTable, listTables, listTasks, updateTask } from '../../api'

const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']
const OPS = {
  text: [['eq', '等于'], ['ne', '不等于'], ['contains', '包含'], ['startswith', '开头是'], ['null', '为空'], ['not_null', '不为空']],
  number: [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'], ['null', '为空'], ['not_null', '不为空']],
  date: [['eq', '等于'], ['gte', '不早于'], ['lte', '不晚于'], ['today', '当天'], ['past_days', '过去 N 天'], ['older_than_days', '早于 N 天前'], ['within_days', '未来 N 天内'], ['null', '为空'], ['not_null', '不为空']],
  bool: [['eq', '等于'], ['null', '为空'], ['not_null', '不为空']],
  select: [['eq', '等于'], ['ne', '不等于'], ['in', '属于（多选）'], ['null', '为空'], ['not_null', '不为空']],
}
const ACTION_TYPES = [['notify', '站内通知'], ['email', '邮件'], ['sms', '短信'], ['webhook', 'Webhook']]
const CRON_PRESETS = [
  { label: '每小时', expr: '0 * * * *' },
  { label: '每天 9 点', expr: '0 9 * * *' },
  { label: '每天 9 点半', expr: '30 9 * * *' },
  { label: '每周一 9 点', expr: '0 9 * * 1' },
]

const editId = ref(null)
const tables = ref([])
const tableIndex = ref(-1)
const tableFields = ref([])
const saving = ref(false)
const aiDesc = ref('')
const aiGenerating = ref(false)
const aiNotes = ref('')

const form = ref(blank())

function blank() {
  return {
    name: '', enabled: false,
    condition_mode: 'structured',
    condition: { logic: 'AND', rules: [] },
    schedule: { type: 'interval', minutes: '60', expr: '0 9 * * *' },
    action: { type: 'notify', template: '', webhook_url: '', recipients: { type: 'fixed', value: '', field: '' } },
    cooldown_hours: '24', max_per_run: '100',
  }
}

onLoad(async (q) => {
  editId.value = q.id ? Number(q.id) : null
  uni.setNavigationBarTitle({ title: editId.value ? '编辑任务' : '新建任务' })
  try {
    tables.value = await listTables()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
  if (editId.value) {
    try {
      const all = await listTasks()
      const t = all.find((x) => x.id === editId.value)
      if (t) await fillForm(t)
    } catch (e) {
      uni.showToast({ title: e.message, icon: 'none' })
    }
  }
})

async function fillForm(t) {
  const c = t.condition || {}
  form.value = {
    name: t.name, enabled: t.enabled,
    condition_mode: t.condition_mode,
    condition: t.condition_mode === 'llm'
      ? { description: c.description || '' }
      : { logic: c.logic || 'AND', rules: (c.rules || []).map((r) => ({ ...r })) },
    schedule: { type: t.schedule?.type || 'interval', minutes: String(t.schedule?.minutes ?? 60), expr: t.schedule?.expr || '0 9 * * *' },
    action: {
      type: t.action?.type || 'notify', template: t.action?.template || '',
      webhook_url: t.action?.webhook_url || '',
      recipients: { type: t.action?.recipients?.type || 'fixed', value: t.action?.recipients?.value || '', field: t.action?.recipients?.field || '' },
    },
    cooldown_hours: String(t.cooldown_hours ?? 24), max_per_run: String(t.max_per_run ?? 100),
  }
  tableIndex.value = tables.value.findIndex((x) => x.id === t.table_id)
  await loadFields(t.table_id)
}

async function loadFields(tid) {
  tableFields.value = []
  if (tid) {
    const t = await getTable(tid).catch(() => null)
    if (t) tableFields.value = t.fields
  }
  rebuildFieldOptions()
}

function onTableChange(e) {
  tableIndex.value = Number(e.detail.value)
  form.value.condition = form.value.condition_mode === 'llm' ? { description: '' } : { logic: 'AND', rules: [] }
  loadFields(tables.value[tableIndex.value].id)
}

const fieldOptions = ref([])

function rebuildFieldOptions() {
  fieldOptions.value = [
    ...tableFields.value.map((f) => ({ field_name: f.field_name, label: f.label })),
    { field_name: 'created_at', label: '创建时间' },
    { field_name: 'updated_at', label: '更新时间' },
  ]
}

function fieldOf(name) {
  if (name === 'created_at' || name === 'updated_at') return { field_name: name, data_type: 'datetime', widget: 'datetime-picker' }
  if (name === 'id') return { field_name: 'id', data_type: 'int', widget: 'number' }
  return tableFields.value.find((f) => f.field_name === name)
}

function fieldLabel(name) {
  if (!name) return ''
  return fieldOf(name)?.label || { created_at: '创建时间', updated_at: '更新时间' }[name] || name
}

function opsFor(fieldName) {
  const f = fieldOf(fieldName)
  const raw = !f ? OPS.text
    : f.widget === 'select' ? OPS.select
    : f.data_type === 'bool' ? OPS.bool
    : ['date', 'datetime'].includes(f.data_type) ? OPS.date
    : ['int', 'decimal'].includes(f.data_type) ? OPS.number
    : OPS.text
  return raw.map(([value, label]) => ({ value, label }))
}

function opLabel(r) {
  return opsFor(r.field).find((o) => o.value === r.op)?.label || r.op || '操作'
}

function selectOptions(f) {
  return (f?.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
}

function onRuleField(r, e) {
  r.field = fieldOptions.value[Number(e.detail.value)].field_name
  r.value = null
}

async function aiGenerate() {
  if (tableIndex.value < 0) return uni.showToast({ title: '请先选择数据表', icon: 'none' })
  if (!aiDesc.value.trim()) return uni.showToast({ title: '请描述任务需求', icon: 'none' })
  aiGenerating.value = true
  uni.showLoading({ title: 'AI 设计中…', mask: true })
  try {
    const r = await aiAssistTask(tables.value[tableIndex.value].id, aiDesc.value.trim())
    aiNotes.value = r.notes || ''
    const t = {
      name: r.name, table_id: tables.value[tableIndex.value].id, enabled: false,
      condition_mode: r.condition_mode, condition: r.condition,
      schedule: r.schedule, action: r.action, cooldown_hours: r.cooldown_hours, max_per_run: 100,
    }
    await fillForm(t)
    uni.showToast({ title: '已生成，可继续调整', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
    aiGenerating.value = false
  }
}

async function save() {
  const f = form.value
  if (!f.name.trim()) return uni.showToast({ title: '请填写任务名称', icon: 'none' })
  if (tableIndex.value < 0) return uni.showToast({ title: '请选择数据表', icon: 'none' })
  const payload = {
    name: f.name.trim(),
    table_id: tables.value[tableIndex.value].id,
    enabled: f.enabled,
    condition_mode: f.condition_mode,
    condition: f.condition_mode === 'llm'
      ? { description: f.condition.description || '' }
      : { logic: f.condition.logic, rules: f.condition.rules.filter((r) => r.field && r.op) },
    schedule: f.schedule.type === 'interval'
      ? { type: 'interval', minutes: Number(f.schedule.minutes) || 60 }
      : { type: 'cron', expr: f.schedule.expr },
    action: {
      type: f.action.type, template: f.action.template,
      webhook_url: f.action.webhook_url || undefined,
      recipients: f.action.recipients,
    },
    cooldown_hours: Number(f.cooldown_hours) || 0,
    max_per_run: Number(f.max_per_run) || 100,
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateTask(editId.value, payload)
    } else {
      await createTask(payload)
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
.ai-box { background: #faf5ff; border: 1rpx solid #e9d5ff; border-radius: 16rpx; padding: 20rpx; margin-bottom: 16rpx; }
.ai-textarea { font-size: 26rpx; color: #303133; width: 100%; min-height: 100rpx; }
.ai-btn {
  margin-top: 12rpx; text-align: center; background: linear-gradient(135deg, #7c3aed, #a855f7);
  color: #fff; font-size: 28rpx; padding: 14rpx 0; border-radius: 32rpx;
}
.ai-notes { font-size: 22rpx; color: #e6a23c; margin-top: 12rpx; }
.form-item { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; }
.label { font-size: 26rpx; color: #606266; margin-bottom: 12rpx; }
.required { color: #f56c6c; }
.input { font-size: 30rpx; color: #303133; }
.textarea { font-size: 28rpx; color: #303133; width: 100%; min-height: 140rpx; }
.picker-value { font-size: 30rpx; color: #303133; padding: 8rpx 0; }
.placeholder { color: #c0c4cc; }
.radio-row { display: flex; gap: 12rpx; flex-wrap: wrap; }
.radio {
  font-size: 26rpx; color: #606266; border: 1rpx solid #dcdfe6; border-radius: 32rpx; padding: 12rpx 28rpx;
}
.radio.sm { font-size: 24rpx; padding: 8rpx 24rpx; }
.radio.active { background: #409eff; border-color: #409eff; color: #fff; }
.cond-card { border: 1rpx solid #ebeef5; border-radius: 12rpx; padding: 16rpx; margin-bottom: 12rpx; }
.fc-row { display: flex; gap: 12rpx; align-items: center; margin-bottom: 12rpx; }
.fc-row:last-child { margin-bottom: 0; }
.fc-picker { font-size: 24rpx; color: #409eff; border: 1rpx solid #b3d8ff; border-radius: 8rpx; padding: 10rpx 16rpx; max-width: 300rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fc-picker.wide { flex: 1; }
.fc-input { flex: 1; font-size: 26rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 8rpx; padding: 12rpx 16rpx; }
.fc-del { font-size: 24rpx; color: #f56c6c; padding: 4rpx 8rpx; }
.add-field { text-align: center; color: #409eff; font-size: 26rpx; border: 1rpx dashed #b3d8ff; border-radius: 12rpx; padding: 16rpx; }
.preset-row { display: flex; gap: 12rpx; flex-wrap: wrap; margin-top: 12rpx; }
.preset { font-size: 22rpx; color: #409eff; background: #ecf5ff; border-radius: 24rpx; padding: 6rpx 20rpx; }
.chip-row { display: flex; gap: 10rpx; flex-wrap: wrap; margin-top: 12rpx; }
.chip { font-size: 22rpx; color: #606266; background: #f5f7fa; border-radius: 8rpx; padding: 6rpx 16rpx; }
.hint-text { font-size: 22rpx; color: #909399; }
.lbl { font-size: 26rpx; color: #606266; width: 200rpx; }
.save-btn { background: #409eff; color: #fff; border-radius: 48rpx; font-size: 32rpx; margin-top: 8rpx; }
.save-btn[disabled] { background: #a0cfff; }
</style>
