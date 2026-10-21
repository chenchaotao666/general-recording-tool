<template>
  <!-- 自动化抽屉（§11.3 完整版入口：右上工具栏时钟图标）：规则列表 ⇄ 编辑器 ⇄ 运行日志
       编辑器头部：‹ 名称输入框 ｜ ☰ 运行日志 ｜ ✕（对齐参照 右上角工具栏-新建自动化提醒.png） -->
  <transition name="ad-slide">
    <div v-if="visible" class="ad st-side-panel" :style="{ width: `${panelWidth}px` }">
      <div class="st-side-resize" :class="{ active: resizing }" data-smart-tip="拖动调整宽度" @mousedown.prevent="startResize" />
      <!-- 列表 -->
      <template v-if="mode === 'list'">
        <div class="ad-head">
          <span class="ad-title">自动化</span>
          <span class="ad-x st-icon-action" @click="emit('close')"><StIcon name="close" :size="18" /></span>
        </div>
        <div v-loading="loading" class="ad-body ad-body-list">
          <div class="ad-list-toolbar"><span>{{ rules.length }} 条自动化流程，{{ rules.filter(r => r.last_run?.status === 'running').length }} 条运行中</span><el-button type="primary" @click="mode = 'templates'">新建流程</el-button></div>
          <div v-if="!rules.length && !loading" class="ad-empty">
            <StIcon name="automation" :size="40" />
            <div>还没有自动化规则</div>
            <div class="ad-empty-s">定时提醒、记录新增/变更时发消息、自动修改记录……</div>
          </div>
          <div v-for="r in rules" :key="r.id" class="ad-rule" @click="edit(r)">
            <div class="ad-r-main">
              <div class="ad-r-name">{{ r.name }}</div>
              <div class="ad-r-sum"><template v-if="r.trigger.type !== 'schedule'">当 <span class="ad-chip"><StIcon name="view-grid" :size="13" />{{ tableName }}</span> 里 </template><span class="ad-chip">{{ summary(r) }}</span>，就{{ r.actions.map(a => ACT_LABELS[a.type]).join('、') }}。</div>
              <div v-if="r.last_run" class="ad-r-last" :class="r.last_run.status">
                最近运行：{{ r.last_run.started_at?.slice(5, 16) }} · {{ STATUS[r.last_run.status] || r.last_run.status }}
              </div>
            </div>
            <el-switch :model-value="r.enabled" size="small" @click.stop @update:model-value="(v) => toggle(r, v)" />
            <el-dropdown :hide-after="0" trigger="click" @command="(c) => ruleAction(c, r)" @click.stop>
              <span class="ad-more st-icon-action" @click.stop><StIcon name="more-h" :size="16" /></span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">编辑</el-dropdown-item>
                  <el-dropdown-item v-if="r.trigger?.type === 'schedule'" command="run">立即运行一次</el-dropdown-item>
                  <el-dropdown-item command="logs">运行日志</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <template v-else-if="mode === 'templates'">
        <div class="ad-head">
          <button class="ad-back" aria-label="返回" @click="back"><StIcon name="back" :size="18" /></button>
          <span class="ad-title">新建流程</span>
          <button class="ad-x" aria-label="关闭" @click="emit('close')"><StIcon name="close" :size="18" /></button>
        </div>
        <div class="ad-body ad-templates">
          <button class="ad-template ad-template-blank" @click="newRule('blank')"><StIcon name="plus" :size="22" />空白流程</button>
          <button v-for="t in templates" :key="t.kind" class="ad-template" @click="newRule(t.kind)">
            <strong>{{ t.name }}</strong><span>{{ t.description }}</span>
          </button>
        </div>
      </template>
      <!-- 编辑器 / 运行日志 -->
      <template v-else>
        <div class="ad-head ad-head-edit">
          <span class="ad-back st-icon-action" @click="back"><StIcon name="back" :size="18" /></span>
          <input v-if="mode === 'edit'" v-model="draft.name" class="ad-name" maxlength="200" placeholder="自动化名称" />
          <span v-else class="ad-title">运行日志 · {{ draft?.name }}</span>
          <span v-if="mode === 'edit' && draft.id" class="ad-log" @click="openLogs(draft)"><StIcon name="log" :size="16" />运行日志</span>
          <span class="ad-vsep" />
          <span class="ad-x st-icon-action" @click="emit('close')"><StIcon name="close" :size="18" /></span>
        </div>
        <div class="ad-body ad-body-edit">
          <AutomationEditor v-if="mode === 'edit'" v-model="draft" :table-id="tableId" :table-name="tableName" :fields="fields"
                            :tables="tables" :members="members" :dashboards="dashboards" :load-fields="loadFields" />
          <AutomationRunLogs v-else ref="runLogsRef" :rule-id="draft.id" :trigger-type="draft.trigger?.type" />
        </div>
        <div v-if="mode === 'edit'" class="ad-foot">
          <span v-if="enableError" class="ad-save-error" role="alert"><span aria-hidden="true">!</span>{{ enableError }}</span>
          <span v-else-if="loopWarning" class="ad-save-error ad-save-warning" role="status"><span aria-hidden="true">!</span>{{ loopWarning }}</span>
          <el-button v-if="draft.trigger?.type === 'schedule'" :disabled="!canSave || !!enableError || saving" :loading="running" @click="runOnce(draft, true)">试运行</el-button>
          <span class="ad-foot-sp" />
          <el-button :disabled="!canSave || saving" @click="save(false)">仅保存</el-button>
          <el-button type="primary" :disabled="!canSave || !!enableError" :loading="saving" @click="save(true)">保存并启用</el-button>
        </div>
      </template>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import AutomationEditor from './AutomationEditor.vue'
import AutomationRunLogs from './AutomationRunLogs.vue'
import { usePanelResize } from '../../../smart/utils/usePanelResize.js'
import { smartCreateAutomation, smartDeleteAutomation, smartListAutomations,
         smartRunAutomation, smartUpdateAutomation } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  tableId: Number,
  tableName: String,
  fields: { type: Array, default: () => [] },
  tables: { type: Array, default: () => [] },
  members: { type: Array, default: () => [] },
  dashboards: { type: Array, default: () => [] },
  loadFields: { type: Function, required: true },
  initialDraft: { type: Object, default: null },   // 精简版「更多配置 ›」/表单「设置自动化提醒」带入的草稿
})
const emit = defineEmits(['close', 'run-complete'])
const { panelWidth, resizing, startResize, stopResize } = usePanelResize('st-automation-panel-width', 580)
watch(() => props.visible, visible => { if (!visible) stopResize() })

const STATUS = { success: '成功', partial: '部分成功', failed: '失败', skipped: '已跳过', running: '运行中' }
const ACT_LABELS = { sendMessage: '发送消息', findRecords: '查找记录', createRecord: '新增记录', updateRecords: '修改记录' }
const mode = ref('list')
const rules = ref([])
const draft = ref(null)
const runLogsRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
let logsFrom = 'list'
const enableError = computed(() => {
  const actions = draft.value?.actions || []
  if (actions.at(-1)?.type === 'findRecords') return '最后一步不能为查找记录，请调整后再启用。'
  return ''
})
const loopWarning = computed(() => {
  const trigger = draft.value?.trigger || {}
  if (!trigger.triggerByAutomation) return ''
  const actions = draft.value?.actions || []
  const specified = trigger.watchMode === 'specified' || (!trigger.watchMode && (trigger.watchConditions?.length || trigger.watchFields?.length))
  const watched = new Set(trigger.watchConditions?.map(c => c.fieldId) ?? trigger.watchFields ?? [])
  const index = actions.findIndex(a => {
    if (String(a.tableId || props.tableId) !== String(props.tableId)) return false
    if (trigger.type === 'recordCreated') return a.type === 'createRecord'
    return trigger.type === 'recordUpdated' && a.type === 'updateRecords'
      && a.values?.some(v => v.fieldId && (!specified || watched.has(v.fieldId)))
  })
  return index < 0 ? '' : `已允许自动化再次触发，第 ${index + 2} 步可能触发本流程；仅在数据实际变化且满足条件时执行，并受递归深度限制。`
})
const canSave = computed(() => Boolean(draft.value?.name?.trim() && draft.value?.trigger?.type && draft.value?.actions?.length))
const templates = [
  { kind: 'recordUpdated', name: '记录变更提醒', description: '当记录内容变更时，发送消息通知。' },
  { kind: 'recordCreated', name: '添加记录提醒', description: '添加新记录时，向指定成员发送消息通知。' },
  { kind: 'schedule', name: '定时提醒', description: '每天在指定时间，定时发送提醒消息。' },
  { kind: 'defaults', name: '新记录设置默认值', description: '添加新记录时，自动填写指定内容。' },
  { kind: 'sync', name: '联动修改', description: '当记录内容变更时，同步修改其他内容。' },
]

function labelOf(fn) { return props.fields.find(f => f.field_name === fn)?.label || fn }
function summary(r) {
  const t = r.trigger
  let head
  if (t.type === 'schedule') {
    const s = t.schedule || {}
    head = `${{ daily: '每天', weekly: '每周', monthly: '每月', weekdays: '每工作日' }[s.freq] || ''} ${s.time} 定时触发`
  } else if (t.type === 'recordCreated') head = '添加新记录时'
  else {
    const watched = t.watchMode === 'any' ? [] : (t.watchConditions?.map(c => c.fieldId).filter(Boolean) ?? t.watchFields ?? [])
    head = watched.length ? `「${[...new Set(watched)].map(labelOf).join('、')}」有变更时` : t.watchMode === 'specified' ? '指定列有变更时' : '记录内容变更时'
  }
  return head
}

async function load() {
  loading.value = true
  try { rules.value = (await smartListAutomations(props.tableId)).automations } finally { loading.value = false }
}
watch(() => props.visible, (v) => {
  if (!v) return
  load()
  if (props.initialDraft) { draft.value = JSON.parse(JSON.stringify(props.initialDraft)); mode.value = 'edit' }
  else mode.value = 'list'
})
watch(() => props.initialDraft, (d) => {
  if (d && props.visible) { draft.value = JSON.parse(JSON.stringify(d)); mode.value = 'edit' }
})

const uid = () => `a${Date.now().toString(36)}`
function newRule(kind) {
  const msg = (title) => ({ id: uid(), type: 'sendMessage', channel: 'docMessage', to: [], toFields: [], webhookUrl: '', title, content: [{ t: 'text', v: '请查看文档内容' }], buttons: [] })
  const presets = {
    schedule: { name: '定时提醒', trigger: { type: 'schedule', schedule: { freq: 'daily', time: '09:00', weekdays: [1], monthDays: [1] } }, actions: [msg('定时提醒')] },
    recordCreated: { name: '新记录提醒', trigger: { type: 'recordCreated', rowConditions: props.fields[0] ? [{ fieldId: props.fields[0].field_name, operator: 'isNotEmpty' }] : [], filter: { match: 'all', conditions: [] } }, actions: [msg('新记录提醒')] },
    recordUpdated: { name: '记录修改提醒', trigger: { type: 'recordUpdated', watchFields: [], filter: { match: 'all', conditions: [] } }, actions: [msg('记录修改提醒')] },
  }
  const p = presets[kind] || (kind === 'blank'
    ? { name: '空白流程', trigger: { type: '' }, actions: [] }
    : { name: kind === 'defaults' ? '新记录设置默认值' : '联动修改',
        trigger: presets[kind === 'defaults' ? 'recordCreated' : 'recordUpdated'].trigger,
        actions: [{ id: uid(), type: 'updateRecords', tableId: props.tableId, target: 'triggered', match: 'all', conditions: [], values: [] }] })
  draft.value = { enabled: true, ...JSON.parse(JSON.stringify(p)) }
  mode.value = 'edit'
}
function edit(r) { draft.value = JSON.parse(JSON.stringify(r)); mode.value = 'edit' }
function back() {
  if (mode.value === 'logs' && runLogsRef.value?.back()) return
  if (mode.value === 'logs' && logsFrom === 'edit') { mode.value = 'edit'; return }
  mode.value = 'list'
  load()
}

async function save(enabled) {
  if (!canSave.value || saving.value || (enabled && enableError.value)) return
  const d = draft.value
  saving.value = true
  try {
    const actions = d.actions.map(a => a.type === 'sendMessage' ? { ...a, channel: 'docMessage', webhookUrl: '' } : a)
    const payload = { name: d.name.trim(), enabled, trigger: d.trigger, actions }
    const r = d.id ? await smartUpdateAutomation(d.id, payload) : await smartCreateAutomation(props.tableId, payload)
    draft.value = JSON.parse(JSON.stringify(r.automation))
    ElMessage.success(enabled ? '流程已保存并启用' : '流程已保存，暂未启用')
    mode.value = 'list'
    load()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
async function toggle(r, v) {
  await smartUpdateAutomation(r.id, { enabled: v })
  r.enabled = v
  ElMessage.success(v ? '已启用' : '已停用')
}
async function runOnce(r, saveDraft = false) {
  if (r.trigger?.type !== 'schedule' || running.value || saving.value) return
  if (saveDraft && (!canSave.value || enableError.value)) return
  running.value = true
  try {
    let ruleId = r.id
    if (saveDraft) {
      const payload = {
        name: r.name.trim(), enabled: r.id ? Boolean(r.enabled) : false, trigger: r.trigger,
        actions: r.actions.map(a => a.type === 'sendMessage' ? { ...a, channel: 'docMessage', webhookUrl: '' } : a),
      }
      const saved = r.id ? await smartUpdateAutomation(r.id, payload) : await smartCreateAutomation(props.tableId, payload)
      draft.value = JSON.parse(JSON.stringify(saved.automation))
      ruleId = saved.automation.id
    }
    const { run } = await smartRunAutomation(ruleId)
    emit('run-complete')
    ElMessage[run.status === 'success' ? 'success' : 'warning'](`运行${STATUS[run.status] || run.status}`)
    load()
  } catch (e) {
    ElMessage.error(e.message || '运行失败')
  } finally {
    running.value = false
  }
}
function openLogs(r) {
  logsFrom = mode.value
  if (mode.value === 'list') draft.value = JSON.parse(JSON.stringify(r))
  mode.value = 'logs'

}
async function ruleAction(cmd, r) {
  if (cmd === 'edit') edit(r)
  else if (cmd === 'run') runOnce(r)
  else if (cmd === 'logs') openLogs(r)
  else if (cmd === 'delete') {
    await ElMessageBox.confirm(`删除自动化「${r.name}」？运行日志将一并删除。`, '删除', { type: 'warning' })
    await smartDeleteAutomation(r.id)
    ElMessage.success('已删除')
    load()
  }
}
</script>

<style scoped>
.ad { position: relative; max-width: 100%; flex-shrink: 0; min-height: 0; box-sizing: border-box; overflow: hidden; background: #F7F7F9;
      display: flex; flex-direction: column; --el-color-primary: var(--st-primary); }
.ad-head { display: flex; align-items: center; gap: 12px; padding: 14px 24px; background: #fff; border-bottom: 1px solid var(--st-border); flex-shrink: 0; }
.ad-title { font-size: 17px; font-weight: 700; flex: 1; }
.ad-x, .ad-back { cursor: pointer; display: inline-flex; color: var(--st-text-1); }
.ad-name { flex: 1; height: 36px; border: 1px solid var(--st-border); border-radius: 6px; padding: 0 10px; font-size: 17px; font-weight: 700; outline: none; }
.ad-name:focus { border-color: var(--st-primary); }
.ad-log { display: inline-flex; align-items: center; gap: 6px; font-size: 15px; color: var(--st-text-2); cursor: pointer; white-space: nowrap; }
.ad-log:hover { color: var(--st-text-1); }
.ad-vsep { width: 1px; height: 16px; background: var(--st-border); }
.ad-body { flex: 1; min-height: 0; overflow: auto; padding: 14px 24px; }
.ad-body-edit { min-width: 0; overflow-x: hidden; padding: 0 24px; }
.ad-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 60px 0; color: var(--st-text-3); font-size: 14px; }
.ad-empty .st-icon { color: var(--st-text-4); }
.ad-empty-s { font-size: 12px; color: var(--st-text-4); }
.ad-rule { display: flex; align-items: flex-start; gap: 12px; background: #fff; border-radius: 5px; padding: 16px 20px; margin-bottom: 8px; cursor: pointer; border: 1px solid var(--st-border); }
.ad-rule:hover { border-color: #cbd3df; box-shadow: 0 2px 8px #00000008; }
.ad-r-ico { width: 26px; height: 26px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; color: #fff; flex: none; }
.ad-r-main { flex: 1; min-width: 0; }
.ad-r-name { font-size: 16px; font-weight: 600; color: var(--st-text-1); }
.ad-r-sum { font-size: 14px; color: var(--st-text-2); margin-top: 10px; line-height: 1.8; }
.ad-r-last { font-size: 12px; color: var(--st-text-3); margin-top: 4px; }
.ad-r-last.failed { color: var(--el-color-danger); }
.ad-more { display: inline-flex; padding: 2px; cursor: pointer; color: var(--st-text-2); }
.ad-foot { display: flex; align-items: center; gap: 8px; padding: 12px 20px; background: #fff; border-top: 1px solid var(--st-border); }
.ad-foot-sp { flex: 1; }
.ad-save-error { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 13px; color: var(--st-text-2); }
.ad-save-error > span { display: inline-flex; align-items: center; justify-content: center; flex: none; width: 18px; height: 18px; border-radius: 50%; background: var(--el-color-danger); color: #fff; font-weight: 700; }
.ad-save-warning > span { background: var(--el-color-warning); }
.ad-slide-enter-active, .ad-slide-leave-active { transition: opacity .15s ease; }
.ad-slide-leave-active { transition-duration: var(--st-panel-close-duration, 80ms); }
.ad-slide-enter-from, .ad-slide-leave-to { opacity: 0; }
.ad-body-list { background: #fff; }
.ad-chip { display: inline-flex; align-items: center; gap: 4px; padding: 1px 5px; border: 1px solid var(--st-border); border-radius: 4px; background: #f7f7f8; }
.ad-list-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; font-size: 14px; color: var(--st-text-2); }
.ad-templates { padding: 14px 20px; }
.ad-template { width: 100%; text-align: left; display: flex; flex-direction: column; gap: 10px; padding: 18px 20px; margin-bottom: 8px; background: #fff; border: 1px solid var(--st-border); border-radius: 5px; cursor: pointer; color: var(--st-text-1); font: inherit; }
.ad-template strong { font-size: 16px; }
.ad-template > span { font-size: 14px; line-height: 1.7; color: var(--st-text-2); }
.ad-template:hover { box-shadow: 0 4px 12px #0000000d; border-color: #cbd3df; }
.ad-template-blank { flex-direction: row; align-items: center; color: var(--st-primary); font-size: 17px; font-weight: 600; padding: 24px 24px; }
button.ad-back, button.ad-x { border: 0; background: transparent; padding: 0; }
.ad-name { min-width: 0; }
.ad-foot { flex-shrink: 0; }
.ad :deep(.el-button) { min-height: 36px; }
@media (max-width: 520px) { .ad-body-edit { padding: 0 16px; } .ad-foot { padding-right: 24px; } .ad-log { font-size: 12px; } }
</style>
