<template>
  <div class="arl">
    <template v-if="!selected">
      <div class="arl-filters">
        <el-date-picker class="st-control" v-model="dates" type="daterange" value-format="YYYY-MM-DD" format="YYYY/MM/DD"
                        range-separator="-" start-placeholder="开始日期" end-placeholder="结束日期"
                        :shortcuts="shortcuts" :disabled-date="futureDate" @change="reload" />
        <el-select class="st-control" v-model="statuses" multiple collapse-tags collapse-tags-tooltip placeholder="全部状态" clearable @change="reload">
          <el-option v-for="(label, key) in STATUS" :key="key" :value="key" :label="label" />
        </el-select>
        <el-select class="st-control" v-model="duration" placeholder="运行耗时" clearable @change="reload">
          <el-option v-for="o in DURATIONS" :key="o.value" v-bind="o" />
        </el-select>
        <el-button class="st-button st-button--icon arl-refresh" :loading="loading" aria-label="刷新运行日志" @click="load">
          <StIcon v-if="!loading" name="refresh" :size="18" />
        </el-button>
      </div>
      <div v-loading="loading" class="arl-table-wrap">
        <table class="arl-table">
          <thead><tr><th>日志产生时间</th><th>运行状态</th><th>运行耗时</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id">
              <td>{{ formatTime(run.started_at) }}</td>
              <td><span class="arl-status" :class="run.status"><i>{{ statusIcon(run.status) }}</i>{{ STATUS[run.status] || run.status }}</span></td>
              <td>{{ elapsed(run) }}</td>
              <td><button class="st-button arl-link" @click="selected = run">详情</button></td>
            </tr>
          </tbody>
        </table>
        <el-empty v-if="!loading && !runs.length && !error" description="暂无符合条件的运行记录" :image-size="64" />
        <div v-if="error" class="arl-error">{{ error }} <button class="st-button arl-link" @click="load">重试</button></div>
      </div>
      <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total"
                     layout="total, prev, pager, next" small @current-change="load" />
    </template>
    <template v-else>
      <div class="arl-summary">
        <div><h3>{{ formatTime(selected.started_at) }}</h3><p>运行耗时：{{ elapsed(selected) }}<span class="arl-id">ID：{{ selected.id }}</span></p></div>
        <span class="arl-status" :class="selected.status"><i>{{ statusIcon(selected.status) }}</i>{{ STATUS[selected.status] || selected.status }}</span>
      </div>
      <div v-if="selected.error" class="arl-error">{{ selected.error }}</div>
      <details class="arl-step" open>
        <summary><span class="arl-step-icon trigger"><StIcon name="automation" :size="15" /></span>{{ triggerLabel }}<span class="arl-step-state">已触发</span></summary>
        <div class="arl-step-body"><div>触发时间：{{ formatTime(selected.started_at) }}</div><div v-if="selected.trigger_snapshot?.operator">操作人：{{ selected.trigger_snapshot.operator }}</div></div>
      </details>
      <details v-for="s in selected.step_results" :key="s.step" class="arl-step" open>
        <summary><span class="arl-step-icon" :class="s.type"><StIcon :name="ACTION_ICONS[s.type] || 'automation'" :size="15" /></span>
          第{{ s.step }}步 · {{ ACTIONS[s.type] || s.type }}
          <span class="arl-status" :class="s.status"><i>{{ statusIcon(s.status) }}</i></span>
        </summary>
        <div class="arl-step-body">
          <div>运行耗时：{{ s.duration_ms == null ? '未记录' : formatDuration(s.duration_ms) }}</div>
          <div v-if="s.started_at || s.finished_at" class="arl-step-times"><span>开始：{{ formatTime(s.started_at) }}</span><span>结束：{{ formatTime(s.finished_at) }}</span></div>
          <div class="arl-result" :class="{ failed: s.status === 'failed' }">{{ s.message }}</div>
        </div>
      </details>
      <div v-if="!selected.step_results?.length" class="arl-muted">{{ selected.status === 'running' ? '流程正在运行，返回列表刷新后查看最新结果' : '暂无步骤记录' }}</div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import { smartAutomationRuns } from '../../../api/index.js'

const props = defineProps({ ruleId: { type: Number, required: true }, triggerType: String })
const STATUS = { success: '运行成功', failed: '运行失败', partial: '部分成功', running: '运行中', skipped: '已跳过' }
const ACTIONS = { sendMessage: '发送消息', findRecords: '查找记录', createRecord: '新增记录', updateRecords: '修改记录' }
const ACTION_ICONS = { sendMessage: 'comment', findRecords: 'search', createRecord: 'plus', updateRecords: 'pencil' }
const DURATIONS = [{ value: 'lt1', label: '1 分钟以内' }, { value: '1to3', label: '1–3 分钟' },
  { value: '3to10', label: '3–10 分钟' }, { value: '10to60', label: '10–60 分钟' }, { value: 'gte60', label: '60 分钟以上' }]
const localDay = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
function range(days, offset = 0) {
  const end = new Date(); end.setDate(end.getDate() - offset)
  const start = new Date(end); start.setDate(start.getDate() - days + 1)
  return [start, end]
}
const shortcuts = [{ text: '今天', value: () => range(1) }, { text: '昨天', value: () => range(1, 1) },
  { text: '过去3天', value: () => range(3) }, { text: '过去7天', value: () => range(7) }]
const futureDate = d => localDay(d) > localDay(new Date())
const dates = ref(range(7).map(localDay))
const statuses = ref([])
const duration = ref('')
const page = ref(1)
const runs = ref([])
const total = ref(0)
const selected = ref(null)
const loading = ref(false)
const error = ref('')
const triggerLabel = computed(() => ({ recordCreated: '添加新记录时', recordUpdated: '记录内容变更时', schedule: '定时重复' }[selected.value?.trigger_snapshot?.event_type || props.triggerType] || '流程触发'))
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await smartAutomationRuns(props.ruleId, {
      page: page.value, limit: 20, start_date: dates.value?.[0], end_date: dates.value?.[1],
      statuses: statuses.value.join(',') || undefined, duration: duration.value || undefined,
    })
    if (id !== requestId) return
    runs.value = result.runs
    total.value = result.total ?? result.runs.length
  } catch (e) {
    if (id === requestId) { runs.value = []; total.value = 0; error.value = e.message || '日志加载失败' }
  } finally { if (id === requestId) loading.value = false }
}
function reload() { page.value = 1; load() }
function formatTime(value) { return value ? value.replace('T', ' ').slice(0, 19) : '—' }
function formatDuration(ms) {
  if (ms < 1000) return `${Math.round(ms)} 毫秒`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} 秒`
  return `${Math.floor(ms / 60000)} 分 ${Math.floor(ms % 60000 / 1000)} 秒`
}
function elapsed(run) {
  if (!run.finished_at) return run.status === 'running' ? '运行中' : '—'
  const ms = new Date(run.finished_at.replace(' ', 'T')) - new Date(run.started_at.replace(' ', 'T'))
  return Number.isFinite(ms) ? formatDuration(Math.max(0, ms)) : '—'
}
const statusIcon = status => ({ success: '✓', failed: '×', partial: '!', running: '◷', skipped: '−' }[status] || '·')
watch(() => props.ruleId, () => { selected.value = null; reload() }, { immediate: true })
onBeforeUnmount(() => { requestId++ })
defineExpose({ back() { if (!selected.value) return false; selected.value = null; return true } })
</script>

<style scoped>
.arl { padding: 16px 0 24px; }
.arl-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.arl-filters :deep(.el-date-editor) { width: 100%; flex: 1 0 100%; box-sizing: border-box; height: 36px; }
.arl-filters > .el-select { flex: 1; min-width: 130px; }
.arl-filters :deep(.el-select__wrapper) { min-height: 36px; }
.arl-refresh { width: 36px; padding: 0; margin: 0; }
.arl-table-wrap { min-height: 140px; overflow-x: auto; }
.arl-table { width: 100%; border-collapse: collapse; text-align: left; font-size: var(--st-font-size); white-space: nowrap; }
.arl-table th { font-weight: 400; color: var(--st-text-2); border-bottom: 1px solid var(--st-border); padding: 0 8px 12px; }
.arl-table td { padding: 14px 8px; }
.arl-table th:first-child, .arl-table td:first-child { padding-left: 0; }
.arl-table tr:hover td { background: #eef1f5; }
.arl-status { display: inline-flex; align-items: center; gap: 7px; }
.arl-status i { display: inline-flex; justify-content: center; align-items: center; width: 17px; height: 17px; border-radius: 50%; background: #969ca6; color: #fff; font-style: normal; flex: none; }
.arl-status.success i { background: #20bf55; }
.arl-status.failed i { background: #ed5d5d; }
.arl-status.partial i { background: #e5a12e; }
.arl-status.running i { background: #3485fa; }
.arl-link { border: 0; background: none; padding: 0; font: inherit; color: var(--st-primary); cursor: pointer; }
.arl-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; justify-content: space-between; padding: 4px 0 18px; border-bottom: 1px solid var(--st-border); margin-bottom: 16px; }
.arl-summary h3 { margin: 0 0 8px; font-size: var(--st-font-size); }
.arl-summary p { margin: 0; color: var(--st-text-2); font-size: var(--st-font-size); }
.arl-id { margin-left: 12px; }
.arl-step { background: #fff; border: 1px solid var(--st-border); border-radius: 6px; padding: 16px; margin-bottom: 12px; }
.arl-step summary { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: var(--st-font-size); font-weight: 600; list-style: none; }
.arl-step summary::-webkit-details-marker { display: none; }
.arl-step summary::after { content: '›'; margin-left: auto; color: var(--st-text-3); transform: rotate(90deg); }
.arl-step:not([open]) summary::after { transform: none; }
.arl-step-icon { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; color: #fff; border-radius: 3px; background: #f4b500; }
.arl-step-icon.trigger, .arl-step-icon.createRecord { background: #10bda4; }
.arl-step-icon.findRecords { background: #9b6bf2; }
.arl-step-icon.updateRecords { background: #f77b2d; }
.arl-step-state { font-size: var(--st-font-size); font-weight: 400; color: #20a553; }
.arl-step-body { font-size: var(--st-font-size); color: var(--st-text-2); line-height: 1.9; margin-top: 12px; }
.arl-step-times { display: flex; flex-wrap: wrap; gap: 0 16px; }
.arl-result { white-space: pre-wrap; overflow-wrap: anywhere; }
.arl-result.failed, .arl-error { color: #d74e4e; }
.arl-error { padding: 12px 0; font-size: var(--st-font-size); overflow-wrap: anywhere; }
.arl-muted { color: var(--st-text-3); font-size: var(--st-font-size); padding: 12px 0; }
.arl :deep(.el-pagination) { margin-top: 12px; justify-content: flex-end; }
</style>
