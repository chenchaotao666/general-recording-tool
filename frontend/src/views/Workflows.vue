<template>
  <div class="page">
    <div class="page-head">
      <h2>工作流</h2>
      <div>
        <el-button @click="openTemplates">模板市场</el-button>
        <el-button @click="aiVisible = true">AI 生成</el-button>
        <el-button type="primary" @click="$router.push('/workflows/new')">新建工作流</el-button>
      </div>
    </div>

    <!-- 模板市场对话框 -->
    <el-dialog v-model="tplVisible" title="模板市场 · 一键安装场景工作流" width="720px">
      <div class="tpl-grid" v-loading="tplLoading">
        <el-card v-for="t in templates" :key="t.key" shadow="hover" class="tpl-card">
          <div class="tpl-name">{{ t.name }}</div>
          <div class="tpl-desc">{{ t.description }}</div>
          <div class="tpl-scenario">{{ t.scenario }}</div>
          <div class="tpl-tables">
            <span v-for="tb in t.tables" :key="tb.label" class="tpl-table">
              <el-tag size="small" :type="tb.exists ? 'success' : 'info'" effect="plain">
                {{ tb.label }}{{ tb.exists ? '（已有，复用）' : '（将自动创建）' }}
              </el-tag>
            </span>
          </div>
          <el-button type="primary" size="small" :loading="installingKey === t.key" @click="onInstall(t)">
            安装到我的工作流
          </el-button>
        </el-card>
      </div>
    </el-dialog>

    <!-- AI 生成对话框 -->
    <el-dialog v-model="aiVisible" title="AI 生成工作流" width="560px">
      <el-input v-model="aiDesc" type="textarea" :rows="4"
        placeholder="用一句话描述你想要的自动化流程，例如：&#10;每天早上 9 点查询库存表里数量低于 10 的记录，AI 生成补货建议，发站内通知给我" />
      <div class="ai-examples">
        <span class="hint">试试：</span>
        <el-link v-for="ex in AI_EXAMPLES" :key="ex" type="primary" size="small" class="ex" @click="aiDesc = ex">{{ ex }}</el-link>
      </div>
      <el-alert v-if="aiNotes" :title="`生成说明：${aiNotes}`" type="warning" :closable="false" class="mt" />
      <template #footer>
        <el-button @click="aiVisible = false">取消</el-button>
        <el-button type="primary" :loading="aiLoading" @click="onAiGenerate">生成并进入画布</el-button>
      </template>
    </el-dialog>

    <el-table :data="rows" v-loading="loading" @row-dblclick="(r) => $router.push(`/workflows/${r.id}/edit`)">
      <el-table-column prop="name" label="名称" min-width="150">
        <template #default="{ row }">
          <el-link type="primary" @click="$router.push(`/workflows/${row.id}/edit`)">{{ row.name }}</el-link>
          <div v-if="row.description" class="desc">{{ row.description }}</div>
        </template>
      </el-table-column>
      <el-table-column label="触发方式" width="120">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ triggerLabel(row.trigger) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="节点数" width="80" align="center">
        <template #default="{ row }">{{ row.nodes.length }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="onToggle(row)" />
        </template>
      </el-table-column>
      <el-table-column label="最近执行" min-width="200">
        <template #default="{ row }">
          <template v-if="row.last_run">
            <el-tag :type="statusType(row.last_run.status)" size="small">{{ statusLabel(row.last_run.status) }}</el-tag>
            <span class="last-time">{{ row.last_run.run_at }}</span>
            <span v-if="row.last_run.tokens_used" class="tokens">{{ row.last_run.tokens_used }} tok</span>
            <div v-if="row.last_run.error" class="err">{{ row.last_run.error }}</div>
          </template>
          <span v-else class="desc">未执行</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :loading="runningId === row.id" @click="onRun(row)">执行</el-button>
          <el-button link type="primary" size="small" @click="$router.push(`/workflows/${row.id}/edit`)">编辑</el-button>
          <el-button link type="primary" size="small" @click="openRuns(row)">日志</el-button>
          <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 执行日志抽屉 -->
    <el-drawer v-model="runsVisible" :title="`执行日志 · ${runsRow?.name || ''}`" size="480px">
      <el-table :data="runs" size="small">
        <el-table-column label="时间" width="150">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/workflows/runs/${row.id}`)">{{ row.started_at }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="触发" width="70">
          <template #default="{ row }">{{ TRIGGER_LABELS[row.trigger] || row.trigger }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="token" width="70" align="right">
          <template #default="{ row }">{{ row.tokens_used || '' }}</template>
        </el-table-column>
        <el-table-column label="错误">
          <template #default="{ row }"><span class="err">{{ row.error }}</span></template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiAssistWorkflow, deleteWorkflow, installWorkflowTemplate, listWorkflows, listWorkflowTemplates, runWorkflow, toggleWorkflow, workflowRuns } from '../api'

const AI_EXAMPLES = [
  '每天早上把超期未跟进的客户记录整理成清单发邮件给我',
  '新增客户反馈时，AI 判断紧急程度，紧急的立刻发站内通知',
  '每周一生成上周数据汇总，AI 写一段分析结论发通知',
]

const TRIGGER_LABELS = {
  manual: '手动', schedule: '定时', record: '数据变更', webhook: 'Webhook', test: '试运行',
  interval: '定时', cron: '定时',
}
const STATUS_LABELS = { pending: '排队中', running: '执行中', success: '成功', failed: '失败', waiting: '等待中', cancelled: '已取消' }

const rows = ref([])
const loading = ref(false)
const runningId = ref(null)
const runsVisible = ref(false)
const runs = ref([])
const runsRow = ref(null)
const router = useRouter()

// AI 生成
const aiVisible = ref(false)
const aiDesc = ref('')
const aiLoading = ref(false)
const aiNotes = ref('')

// 模板市场
const tplVisible = ref(false)
const tplLoading = ref(false)
const templates = ref([])
const installingKey = ref('')

async function openTemplates() {
  tplVisible.value = true
  tplLoading.value = true
  try { templates.value = await listWorkflowTemplates() } finally { tplLoading.value = false }
}

async function onInstall(t) {
  installingKey.value = t.key
  try {
    const res = await installWorkflowTemplate(t.key)
    tplVisible.value = false
    await load()
    await ElMessageBox.alert(
      res.notes || '已安装（默认停用，确认无误后启用）',
      `已安装「${res.name}」`,
      { confirmButtonText: '去画布确认' },
    )
    router.push(`/workflows/${res.workflow_id}/edit`)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || e)
  } finally {
    installingKey.value = ''
  }
}

async function onAiGenerate() {
  if (!aiDesc.value.trim()) { ElMessage.warning('请描述你想要的流程'); return }
  aiLoading.value = true
  aiNotes.value = ''
  try {
    const def = await aiAssistWorkflow(aiDesc.value.trim())
    sessionStorage.setItem('grt_wf_draft', JSON.stringify(def))
    aiVisible.value = false
    router.push('/workflows/new?draft=1')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiLoading.value = false
  }
}

const triggerLabel = (t) => TRIGGER_LABELS[t?.type] || t?.type || '手动'
const statusLabel = (s) => STATUS_LABELS[s] || s
const statusType = (s) => ({ success: 'success', failed: 'danger', waiting: 'warning', running: 'primary', pending: 'info' }[s] || 'info')

async function load() {
  loading.value = true
  try { rows.value = await listWorkflows() } finally { loading.value = false }
}

async function onToggle(row) {
  row.enabled = !row.enabled
  try { await toggleWorkflow(row.id) } catch (e) {
    row.enabled = !row.enabled
    ElMessage.error(e.message)
  }
}

async function onRun(row) {
  runningId.value = row.id
  try {
    const r = await runWorkflow(row.id)
    if (r.status === 'success') ElMessage.success(`执行成功，消耗 token：${r.tokens_used}`)
    else ElMessage.warning(`状态：${r.status}${r.error ? `；${r.error}` : ''}`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    runningId.value = null
  }
}

async function openRuns(row) {
  runsRow.value = row
  runs.value = await workflowRuns(row.id)
  runsVisible.value = true
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确定删除工作流「${row.name}」？`, '删除确认', { type: 'warning' })
  await deleteWorkflow(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.page { padding: 20px; }
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-head h2 { margin: 0; }
.desc { font-size: 12px; color: #909399; }
.last-time { margin-left: 8px; font-size: 12px; color: #909399; }
.tokens { margin-left: 8px; font-size: 12px; color: #9b59b6; }
.err { font-size: 12px; color: #f56c6c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
.ai-examples { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px 12px; }
.ai-examples .hint { font-size: 12px; color: #909399; }
.ai-examples .ex { font-size: 12px; }
.mt { margin-top: 10px; }
.tpl-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tpl-card { font-size: 13px; }
.tpl-name { font-weight: 600; margin-bottom: 4px; }
.tpl-desc { color: #606266; margin-bottom: 6px; }
.tpl-scenario { font-size: 12px; color: #909399; margin-bottom: 8px; }
.tpl-tables { margin-bottom: 10px; display: flex; gap: 6px; flex-wrap: wrap; }
</style>
