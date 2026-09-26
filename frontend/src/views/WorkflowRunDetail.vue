<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <el-button link @click="$router.back()"><el-icon><ArrowLeft /></el-icon>返回</el-button>
      <h2>执行详情 · {{ run.workflow_name || `#${run.workflow_id}` }}</h2>
      <div class="spacer" />
      <el-tag v-if="run.status" :type="statusType(run.status)" size="large">{{ statusLabel(run.status) }}</el-tag>
    </div>

    <el-descriptions v-if="run.id" :column="4" border size="small" class="meta">
      <el-descriptions-item label="触发方式">{{ TRIGGER_LABELS[run.trigger] || run.trigger }}</el-descriptions-item>
      <el-descriptions-item label="开始时间">{{ run.started_at }}</el-descriptions-item>
      <el-descriptions-item label="结束时间">{{ run.finished_at || '—' }}</el-descriptions-item>
      <el-descriptions-item label="token 消耗">{{ run.tokens_used || 0 }}</el-descriptions-item>
    </el-descriptions>
    <el-alert v-if="run.error" :title="run.error" type="error" class="meta" :closable="false" />

    <!-- 待审批卡片 -->
    <el-card v-for="nr in waitingApprovals" :key="nr.id" class="approval-card" shadow="never">
      <div class="approval-title">
        <el-icon color="#e6a23c"><WarningFilled /></el-icon>
        <b>{{ nr.output?.approval?.title || '待审批' }}</b>
      </div>
      <el-input v-model="comments[nr.id]" type="textarea" :rows="3" placeholder="审批意见（可选）" class="mb" />
      <el-button type="success" :loading="acting" @click="act(nr, true)">通过</el-button>
      <el-button type="danger" plain :loading="acting" @click="act(nr, false)">驳回</el-button>
    </el-card>

    <!-- 节点轨迹 -->
    <el-timeline v-if="run.node_runs?.length" class="trace">
      <el-timeline-item v-for="nr in run.node_runs" :key="nr.id"
        :type="{ success: 'success', failed: 'danger', waiting: 'warning', running: 'primary' }[nr.status] || 'info'"
        :hollow="nr.status === 'waiting'">
        <div class="nr-head" @click="toggleExpand(nr.id)">
          <b>{{ nr.node_id }}</b>
          <el-tag size="small" effect="plain">{{ NODE_TYPE_NAMES[nr.node_type] || nr.node_type }}</el-tag>
          <el-tag size="small" :type="statusType(nr.status)">{{ statusLabel(nr.status) }}</el-tag>
          <span class="nr-meta">{{ nr.duration_ms }}ms</span>
          <span v-if="nr.tokens_used" class="nr-meta tok">{{ nr.tokens_used }} tok</span>
        </div>
        <div v-if="expanded.has(nr.id)" class="nr-detail">
          <div v-if="nr.error" class="err">{{ nr.error }}</div>
          <div class="io">
            <div class="io-col">
              <div class="io-title">输入（渲染后配置）</div>
              <pre>{{ fmt(nr.input) }}</pre>
            </div>
            <div class="io-col">
              <div class="io-title">输出</div>
              <pre>{{ fmt(nr.output) }}</pre>
            </div>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else-if="!loading" description="暂无节点执行记录" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, WarningFilled } from '@element-plus/icons-vue'
import { approveWorkflowNode, getWorkflowRun, workflowNodeTypes } from '../api'

const TRIGGER_LABELS = { manual: '手动', schedule: '定时', record: '数据变更', webhook: 'Webhook', test: '试运行', form: '表单', sub: '子流程' }
const STATUS_LABELS = { pending: '排队中', running: '执行中', success: '成功', failed: '失败', waiting: '等待中', cancelled: '已取消', skipped: '已跳过' }

const route = useRoute()
const runId = Number(route.params.id)
const run = ref({})
const loading = ref(true)
const acting = ref(false)
const comments = reactive({})
const expanded = reactive(new Set())
const NODE_TYPE_NAMES = reactive({})
let timer = null

const waitingApprovals = computed(() =>
  (run.value.node_runs || []).filter((nr) => nr.node_type === 'approval' && nr.status === 'waiting')
)

const statusLabel = (s) => STATUS_LABELS[s] || s
const statusType = (s) => ({ success: 'success', failed: 'danger', waiting: 'warning', running: 'primary', pending: 'info' }[s] || 'info')
const fmt = (v) => (v === undefined || v === null ? '' : JSON.stringify(v, null, 2))

function toggleExpand(id) {
  expanded.has(id) ? expanded.delete(id) : expanded.add(id)
}

async function load() {
  try {
    run.value = await getWorkflowRun(runId)
    if (['pending', 'running'].includes(run.value.status)) schedulePoll()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function schedulePoll() {
  clearTimeout(timer)
  timer = setTimeout(load, 3000)
}

async function act(nr, approved) {
  acting.value = true
  try {
    await approveWorkflowNode(nr.id, approved, comments[nr.id] || '')
    ElMessage.success(approved ? '已通过，流程继续执行' : '已驳回')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  load()
  try {
    const types = await workflowNodeTypes()
    types.forEach((t) => { NODE_TYPE_NAMES[t.type] = t.name })
  } catch { /* 名称映射失败不影响展示 */ }
})
onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
.page { padding: 20px; max-width: 960px; margin: 0 auto; }
.page-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-head h2 { margin: 0; font-size: 18px; }
.spacer { flex: 1; }
.meta { margin-bottom: 16px; }
.approval-card { margin-bottom: 16px; border-color: #e6a23c; }
.approval-title { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; }
.mb { margin-bottom: 10px; }
.trace { margin-top: 10px; }
.nr-head { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.nr-meta { font-size: 12px; color: #909399; }
.nr-meta.tok { color: #9b59b6; }
.nr-detail { margin-top: 8px; }
.err { color: #f56c6c; font-size: 12px; margin-bottom: 6px; }
.io { display: flex; gap: 12px; }
.io-col { flex: 1; min-width: 0; }
.io-title { font-size: 12px; color: #909399; margin-bottom: 4px; }
pre {
  background: #f5f7fa; border-radius: 6px; padding: 8px; font-size: 12px;
  max-height: 240px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 0;
}
</style>
