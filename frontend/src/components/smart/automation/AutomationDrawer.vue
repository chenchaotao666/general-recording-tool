<template>
  <!-- 自动化抽屉（§11.3 完整版入口：右上工具栏时钟图标）：规则列表 ⇄ 编辑器 ⇄ 运行日志
       编辑器头部：‹ 名称输入框 ｜ ☰ 运行日志 ｜ ✕（对齐参照 右上角工具栏-新建自动化提醒.png） -->
  <transition name="ad-slide">
    <div v-if="visible" class="ad">
      <!-- 列表 -->
      <template v-if="mode === 'list'">
        <div class="ad-head">
          <span class="ad-title">自动化</span>
          <el-dropdown trigger="click" @command="newRule">
            <el-button type="primary" size="small"><StIcon name="plus" :size="13" />新建自动化</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="schedule">定时提醒</el-dropdown-item>
                <el-dropdown-item command="recordCreated">添加新记录时提醒</el-dropdown-item>
                <el-dropdown-item command="recordUpdated">记录变更时提醒</el-dropdown-item>
                <el-dropdown-item command="blank" divided>从空白创建</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span class="ad-x st-icon-action" @click="emit('close')"><StIcon name="close" :size="18" /></span>
        </div>
        <div v-loading="loading" class="ad-body">
          <div v-if="!rules.length && !loading" class="ad-empty">
            <StIcon name="automation" :size="40" />
            <div>还没有自动化规则</div>
            <div class="ad-empty-s">定时提醒、记录新增/变更时发消息、自动修改记录……</div>
          </div>
          <div v-for="r in rules" :key="r.id" class="ad-rule" @click="edit(r)">
            <span class="ad-r-ico" :style="{ background: trigColor(r.trigger.type) }"><StIcon :name="trigIcon(r.trigger.type)" :size="14" /></span>
            <div class="ad-r-main">
              <div class="ad-r-name">{{ r.name }}</div>
              <div class="ad-r-sum">{{ summary(r) }}</div>
              <div v-if="r.last_run" class="ad-r-last" :class="r.last_run.status">
                最近运行：{{ r.last_run.started_at?.slice(5, 16) }} · {{ STATUS[r.last_run.status] || r.last_run.status }}
              </div>
            </div>
            <el-switch :model-value="r.enabled" size="small" @click.stop @update:model-value="(v) => toggle(r, v)" />
            <el-dropdown trigger="click" @command="(c) => ruleAction(c, r)" @click.stop>
              <span class="ad-more st-icon-action" @click.stop><StIcon name="more-h" :size="16" /></span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">编辑</el-dropdown-item>
                  <el-dropdown-item command="run">立即运行一次</el-dropdown-item>
                  <el-dropdown-item command="logs">运行日志</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
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
          <div v-else v-loading="logsLoading" class="ad-logs">
            <div v-if="!runs.length && !logsLoading" class="ad-empty">暂无运行记录</div>
            <div v-for="run in runs" :key="run.id" class="ad-run">
              <div class="ad-run-head">
                <span class="ad-run-tag" :class="run.status">{{ STATUS[run.status] || run.status }}</span>
                <span>{{ run.started_at }}</span>
                <span v-if="run.trigger_snapshot?.operator" class="ad-run-op">触发：{{ run.trigger_snapshot.operator }}</span>
              </div>
              <div v-for="s in run.step_results" :key="s.step" class="ad-run-step">
                <span class="ad-run-dot" :class="s.status" />第{{ s.step }}步 {{ ACT_LABELS[s.type] }}：{{ s.message }}
              </div>
              <div v-if="run.error" class="ad-run-err">{{ run.error }}</div>
            </div>
          </div>
        </div>
        <div v-if="mode === 'edit'" class="ad-foot">
          <el-button v-if="draft.id" :loading="running" @click="runOnce(draft)">试运行</el-button>
          <span class="ad-foot-sp" />
          <el-button @click="back">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        </div>
      </template>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import AutomationEditor from './AutomationEditor.vue'
import { smartAutomationRuns, smartCreateAutomation, smartDeleteAutomation, smartListAutomations,
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
const emit = defineEmits(['close'])

const STATUS = { success: '成功', partial: '部分成功', failed: '失败', skipped: '已跳过', running: '运行中' }
const ACT_LABELS = { sendMessage: '发送消息', findRecords: '查找记录', createRecord: '新增记录', updateRecords: '修改记录' }
const mode = ref('list')
const rules = ref([])
const draft = ref(null)
const runs = ref([])
const loading = ref(false)
const logsLoading = ref(false)
const saving = ref(false)
const running = ref(false)
let logsFrom = 'list'

function trigColor(t) { return { schedule: '#22B35E', recordCreated: '#14B8A6', recordUpdated: '#F77B2D' }[t] || '#999' }
function trigIcon(t) { return { schedule: 'automation', recordCreated: 'plus', recordUpdated: 'pencil' }[t] || 'automation' }
function labelOf(fn) { return props.fields.find(f => f.field_name === fn)?.label || fn }
function summary(r) {
  const t = r.trigger
  let head
  if (t.type === 'schedule') {
    const s = t.schedule || {}
    head = `${{ daily: '每天', weekly: '每周', monthly: '每月' }[s.freq] || ''} ${s.time} 定时触发`
  } else if (t.type === 'recordCreated') head = '添加新记录时'
  else head = t.watchFields?.length ? `「${t.watchFields.map(labelOf).join('、')}」有变更时` : '记录内容变更时'
  return `${head} → ${r.actions.map(a => ACT_LABELS[a.type]).join(' → ')}`
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
    recordCreated: { name: '新记录提醒', trigger: { type: 'recordCreated', rowConditions: [], filter: { match: 'all', conditions: [] } }, actions: [msg('新记录提醒')] },
    recordUpdated: { name: '记录修改提醒', trigger: { type: 'recordUpdated', watchFields: [], filter: { match: 'all', conditions: [] } }, actions: [msg('记录修改提醒')] },
  }
  const p = presets[kind] || { ...presets.recordCreated, name: '自动化' }
  draft.value = { enabled: true, ...JSON.parse(JSON.stringify(p)) }
  mode.value = 'edit'
}
function edit(r) { draft.value = JSON.parse(JSON.stringify(r)); mode.value = 'edit' }
function back() {
  if (mode.value === 'logs' && logsFrom === 'edit') { mode.value = 'edit'; return }
  mode.value = 'list'
  load()
}

async function save() {
  const d = draft.value
  saving.value = true
  try {
    const payload = { name: d.name, enabled: d.enabled !== false, trigger: d.trigger, actions: d.actions }
    const r = d.id ? await smartUpdateAutomation(d.id, payload) : await smartCreateAutomation(props.tableId, payload)
    draft.value = JSON.parse(JSON.stringify(r.automation))
    ElMessage.success('自动化已保存')
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
async function runOnce(r) {
  running.value = true
  try {
    const { run } = await smartRunAutomation(r.id)
    ElMessage[run.status === 'success' ? 'success' : 'warning'](`运行${STATUS[run.status] || run.status}`)
    load()
  } catch (e) {
    ElMessage.error(e.message || '运行失败')
  } finally {
    running.value = false
  }
}
async function openLogs(r) {
  logsFrom = mode.value
  if (mode.value === 'list') draft.value = JSON.parse(JSON.stringify(r))
  mode.value = 'logs'
  logsLoading.value = true
  try { runs.value = (await smartAutomationRuns(r.id)).runs } finally { logsLoading.value = false }
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
.ad { position: fixed; top: 56px; right: 0; bottom: 0; width: 560px; z-index: 2000; background: #F7F8FA; box-shadow: -8px 0 24px rgba(0, 0, 0, .08);
      display: flex; flex-direction: column; --el-color-primary: var(--st-primary); }
.ad-head { display: flex; align-items: center; gap: 12px; padding: 14px 20px; background: #fff; border-bottom: 1px solid var(--st-border); }
.ad-title { font-size: 17px; font-weight: 700; flex: 1; }
.ad-x, .ad-back { cursor: pointer; display: inline-flex; color: var(--st-text-1); }
.ad-name { flex: 1; height: 36px; border: 1px solid var(--st-border); border-radius: 6px; padding: 0 10px; font-size: 17px; font-weight: 700; outline: none; }
.ad-name:focus { border-color: var(--st-primary); }
.ad-log { display: inline-flex; align-items: center; gap: 6px; font-size: 15px; color: var(--st-text-2); cursor: pointer; white-space: nowrap; }
.ad-log:hover { color: var(--st-text-1); }
.ad-vsep { width: 1px; height: 16px; background: var(--st-border); }
.ad-body { flex: 1; overflow: auto; padding: 14px 16px; }
.ad-body-edit { padding: 0 24px; }
.ad-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 60px 0; color: var(--st-text-3); font-size: 14px; }
.ad-empty .st-icon { color: var(--st-text-4); }
.ad-empty-s { font-size: 12px; color: var(--st-text-4); }
.ad-rule { display: flex; align-items: flex-start; gap: 12px; background: #fff; border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; cursor: pointer; border: 1px solid transparent; }
.ad-rule:hover { border-color: var(--st-border); }
.ad-r-ico { width: 26px; height: 26px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; color: #fff; flex: none; }
.ad-r-main { flex: 1; min-width: 0; }
.ad-r-name { font-size: 15px; font-weight: 600; color: var(--st-text-1); }
.ad-r-sum { font-size: 13px; color: var(--st-text-2); margin-top: 2px; }
.ad-r-last { font-size: 12px; color: var(--st-text-3); margin-top: 4px; }
.ad-r-last.failed { color: var(--el-color-danger); }
.ad-more { display: inline-flex; padding: 2px; cursor: pointer; color: var(--st-text-2); }
.ad-foot { display: flex; align-items: center; gap: 8px; padding: 12px 96px 12px 20px; background: #fff; border-top: 1px solid var(--st-border); }  /* 右侧让出全局 AI 悬浮按钮 */
.ad-foot-sp { flex: 1; }
.ad-logs { padding: 14px 0; }
.ad-run { background: #fff; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; font-size: 13px; }
.ad-run-head { display: flex; align-items: center; gap: 10px; color: var(--st-text-2); margin-bottom: 6px; }
.ad-run-op { margin-left: auto; }
.ad-run-tag { padding: 1px 8px; border-radius: 4px; font-size: 12px; background: #E8F7EE; color: #1E7E34; }
.ad-run-tag.failed { background: #FDE3E3; color: #C92A2A; }
.ad-run-tag.partial { background: #FFF2DB; color: #B25009; }
.ad-run-step { display: flex; align-items: center; gap: 8px; padding: 3px 0; color: var(--st-text-1); }
.ad-run-dot { width: 7px; height: 7px; border-radius: 50%; background: #52C41A; }
.ad-run-dot.failed { background: var(--el-color-danger); }
.ad-run-dot.skipped { background: var(--st-text-4); }
.ad-run-err { color: var(--el-color-danger); margin-top: 4px; word-break: break-all; }
.ad-slide-enter-active, .ad-slide-leave-active { transition: transform .2s ease; }
.ad-slide-enter-from, .ad-slide-leave-to { transform: translateX(100%); }
</style>
