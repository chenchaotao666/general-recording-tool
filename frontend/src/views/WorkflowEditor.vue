<template>
  <div class="wf-editor">
    <!-- 顶栏 -->
    <div class="topbar">
      <el-button link @click="$router.push('/workflows')">
        <el-icon><ArrowLeft /></el-icon>返回
      </el-button>
      <el-input v-model="meta.name" placeholder="工作流名称" class="name-input" />
      <el-switch v-model="meta.enabled" active-text="启用" />
      <div class="spacer" />
      <el-button v-if="wfId" :loading="running" @click="doRun(false)">立即执行</el-button>
      <el-button v-if="wfId" :loading="running" @click="doRun(true)">试运行</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </div>

    <div class="body">
      <!-- 左侧：触发器 + 节点面板 -->
      <div class="sidebar">
        <div class="side-section">
          <div class="side-title">触发器</div>
          <el-select v-model="trigger.type" size="small" style="width: 100%">
            <el-option label="手动触发" value="manual" />
            <el-option label="定时触发" value="schedule" />
            <el-option label="记录新增时" value="record_created" />
            <el-option label="记录修改时" value="record_updated" />
            <el-option label="Webhook 回调" value="webhook" />
          </el-select>

          <template v-if="trigger.type === 'schedule'">
            <el-radio-group v-model="trigger.sched_kind" size="small" class="mt">
              <el-radio-button value="interval">间隔</el-radio-button>
              <el-radio-button value="cron">Cron</el-radio-button>
            </el-radio-group>
            <div v-if="trigger.sched_kind === 'interval'" class="mt row">
              <span>每</span>
              <el-input-number v-model="trigger.minutes" :min="1" size="small" controls-position="right" style="width: 100px" />
              <span>分钟</span>
            </div>
            <el-select v-else v-model="trigger.expr" size="small" filterable allow-create class="mt" placeholder="cron 表达式">
              <el-option label="每小时" value="0 * * * *" />
              <el-option label="每天 9:00" value="0 9 * * *" />
              <el-option label="每天 18:00" value="0 18 * * *" />
              <el-option label="每周一 9:00" value="0 9 * * 1" />
            </el-select>
          </template>

          <template v-if="trigger.type === 'record_created' || trigger.type === 'record_updated'">
            <el-select v-model="trigger.table_id" size="small" filterable class="mt" placeholder="监听的数据表"
              @change="loadTriggerFields">
              <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
            </el-select>
            <el-select v-if="trigger.type === 'record_updated'" v-model="trigger.watch_fields" size="small" multiple
              class="mt" placeholder="监听字段（空 = 任意修改）">
              <el-option v-for="f in triggerFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
          </template>

          <template v-if="trigger.type === 'webhook'">
            <div v-if="webhookUrl" class="mt webhook-url">
              <div class="hint">POST 此地址即触发（保存后生效）：</div>
              <el-input :model-value="webhookUrl" size="small" readonly>
                <template #append>
                  <el-button @click="copyWebhook">复制</el-button>
                </template>
              </el-input>
            </div>
            <div v-else class="mt hint">保存后自动生成 Webhook 回调地址</div>
          </template>

          <el-input v-model="meta.description" type="textarea" :rows="2" class="mt" placeholder="描述（可选）" />
        </div>

        <div class="side-section palette">
          <div class="side-title">节点（点击添加到画布）</div>
          <div v-for="[cat, items] in paletteGroups" :key="cat" class="palette-group">
            <div class="palette-cat">{{ CAT_NAMES[cat] || cat }}</div>
            <div v-for="nt in items" :key="nt.type" class="palette-item" :title="nt.description" @click="addNode(nt)">
              <span class="dot" :class="`cat-${nt.category}`" />{{ nt.name }}
            </div>
          </div>
        </div>
      </div>

      <!-- 画布 -->
      <div class="canvas-wrap">
        <VueFlow v-model:nodes="flowNodes" v-model:edges="flowEdges" class="canvas" :delete-key-code="['Backspace', 'Delete']"
          :min-zoom="0.3" :max-zoom="1.6" fit-view-on-init @connect="onConnect" @node-click="onNodeClick"
          @pane-click="selectedId = null" @edge-click="selectedId = null">
          <Background pattern-color="#d4d7de" :gap="16" />
          <Controls />
          <template #node-wf="props">
            <FlowNode v-bind="props" />
          </template>
          <div v-if="!flowNodes.length" class="empty-hint">从左侧点击节点添加到画布，拖动连线串联流程</div>
        </VueFlow>
      </div>

      <!-- 右侧：节点配置 -->
      <div v-if="selectedNode" class="config-panel">
        <div class="config-head">
          <span class="config-title">{{ selectedNode.data.typeName }} · {{ selectedNode.id }}</span>
          <el-button link type="danger" size="small" @click="removeNode(selectedNode.id)">删除节点</el-button>
        </div>
        <el-input :model-value="selectedNode.data.name" placeholder="节点显示名" size="small" class="mb"
          @update:model-value="patchSelected({ name: $event })" />
        <SchemaForm :schema="nodeTypeOf(selectedNode.data.nodeType)?.config_schema" :model-value="selectedNode.data.config"
          :tables="tables" :providers="providers" @update:model-value="patchSelected({ config: $event })" />
        <el-divider content-position="left">失败处理</el-divider>
        <el-select :model-value="selectedNode.data.on_error?.policy || 'stop'" size="small" style="width: 100%"
          @update:model-value="patchSelected({ on_error: { policy: $event, max_attempts: 3, backoff_seconds: 60 } })">
          <el-option label="终止流程（默认）" value="stop" />
          <el-option label="跳过该节点继续" value="continue" />
          <el-option label="自动重试（最多 3 次）" value="retry" />
        </el-select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import {
  createWorkflow, getTable, getWorkflow, listProviders, listTables,
  runWorkflow, testRunWorkflow, updateWorkflow, workflowNodeTypes,
} from '../api'
import FlowNode from '../components/workflow/FlowNode.vue'
import SchemaForm from '../components/workflow/SchemaForm.vue'

const CAT_NAMES = { data: '数据', ai: 'AI', logic: '逻辑', action: '动作', human: '人工' }

const route = useRoute()
const router = useRouter()
const wfId = ref(route.params.id ? Number(route.params.id) : null)

const meta = reactive({ name: '', description: '', enabled: false })
const trigger = reactive({ type: 'manual', sched_kind: 'interval', minutes: 60, expr: '0 9 * * *', table_id: null, watch_fields: [], secret: '' })
const webhookUrl = ref('')
const tables = ref([])
const providers = ref([])
const nodeTypes = ref([])
const triggerFields = ref([])

const flowNodes = ref([])
const flowEdges = ref([])
const selectedId = ref(null)
const saving = ref(false)
const running = ref(false)
const idCounters = {}

const selectedNode = computed(() => flowNodes.value.find((n) => n.id === selectedId.value))
const nodeTypeOf = (t) => nodeTypes.value.find((x) => x.type === t)
const paletteGroups = computed(() => {
  const groups = {}
  for (const nt of nodeTypes.value) (groups[nt.category] ||= []).push(nt)
  return Object.entries(groups)
})

function addNode(nt) {
  idCounters[nt.type] = (idCounters[nt.type] || 0) + 1
  let id = `${nt.type.split('_')[0]}_${idCounters[nt.type]}`
  while (flowNodes.value.some((n) => n.id === id)) id = `${id}x`
  flowNodes.value.push({
    id, type: 'wf',
    position: { x: 120 + flowNodes.value.length * 40, y: 80 + flowNodes.value.length * 60 },
    data: { nodeType: nt.type, typeName: nt.name, category: nt.category, name: nt.name, config: {}, on_error: null },
  })
  selectedId.value = id
}

function onConnect(params) {
  const branch = params.sourceHandle === 'true' || params.sourceHandle === 'false' ? params.sourceHandle : null
  if (flowEdges.value.some((e) => e.source === params.source && e.target === params.target && (e.data?.branch || null) === branch)) return
  flowEdges.value.push({
    id: `e_${params.source}_${branch || 'x'}_${params.target}`,
    source: params.source, target: params.target,
    sourceHandle: params.sourceHandle, targetHandle: params.targetHandle,
    label: branch === 'true' ? '是' : branch === 'false' ? '否' : '',
    data: { branch },
  })
}

function onNodeClick({ node }) { selectedId.value = node.id }

function patchSelected(patch) {
  const n = flowNodes.value.find((x) => x.id === selectedId.value)
  if (n) Object.assign(n.data, patch)
}

function removeNode(id) {
  flowNodes.value = flowNodes.value.filter((n) => n.id !== id)
  flowEdges.value = flowEdges.value.filter((e) => e.source !== id && e.target !== id)
  selectedId.value = null
}

async function loadTriggerFields() {
  if (!trigger.table_id) { triggerFields.value = []; return }
  try { triggerFields.value = (await getTable(trigger.table_id)).fields || [] } catch { triggerFields.value = [] }
}

function buildTrigger() {
  const t = trigger
  if (t.type === 'schedule') {
    return t.sched_kind === 'interval'
      ? { type: 'interval', minutes: t.minutes }
      : { type: 'cron', expr: t.expr }
  }
  if (t.type === 'record_created') return { type: t.type, table_id: t.table_id }
  if (t.type === 'record_updated') return { type: t.type, table_id: t.table_id, watch_fields: t.watch_fields }
  if (t.type === 'webhook') return { type: 'webhook', secret: t.secret || undefined }
  return { type: 'manual' }
}

function applyTrigger(t) {
  t = t || { type: 'manual' }
  trigger.type = t.type || 'manual'
  if (t.type === 'interval' || t.type === 'cron') {
    // 后端 schedule 触发器存的是 {type: interval|cron, ...}（scheduler.trigger_of 格式）
    trigger.type = 'schedule'
    trigger.sched_kind = t.type
    trigger.minutes = t.minutes || 60
    trigger.expr = t.expr || '0 9 * * *'
  } else if (t.type === 'schedule') {
    trigger.sched_kind = t.minutes ? 'interval' : 'cron'
    trigger.minutes = t.minutes || 60
    trigger.expr = t.expr || '0 9 * * *'
  }
  trigger.table_id = t.table_id ?? null
  trigger.watch_fields = t.watch_fields || []
  trigger.secret = t.secret || ''
  if (trigger.table_id) loadTriggerFields()
}

async function save() {
  if (!meta.name.trim()) { ElMessage.warning('请填写工作流名称'); return }
  saving.value = true
  try {
    const payload = {
      name: meta.name.trim(),
      description: meta.description,
      enabled: meta.enabled,
      trigger: buildTrigger(),
      nodes: flowNodes.value.map((n) => ({
        id: n.id, type: n.data.nodeType, name: n.data.name,
        config: n.data.config || {}, on_error: n.data.on_error || undefined,
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      })),
      edges: flowEdges.value.map((e) => ({
        from: e.source, to: e.target, ...(e.data?.branch ? { branch: e.data.branch } : {}),
      })),
    }
    const saved = wfId.value
      ? await updateWorkflow(wfId.value, payload)
      : await createWorkflow(payload)
    wfId.value = saved.id
    webhookUrl.value = saved.webhook_url || ''
    if (saved.trigger?.secret) trigger.secret = saved.trigger.secret
    ElMessage.success('已保存')
    router.replace(`/workflows/${saved.id}/edit`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function doRun(isTest) {
  running.value = true
  try {
    const r = isTest ? await testRunWorkflow(wfId.value) : await runWorkflow(wfId.value)
    const ok = r.status === 'success'
    ElMessageBox({
      title: ok ? '执行完成' : '执行未成功',
      message: `状态：${r.status}${r.error ? `；${r.error}` : ''}；消耗 token：${r.tokens_used}`,
      confirmButtonText: '查看详情',
      cancelButtonText: '关闭',
      showCancelButton: true,
      type: ok ? 'success' : 'warning',
    }).then(() => router.push(`/workflows/runs/${r.id}`)).catch(() => {})
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}

function copyWebhook() {
  const url = `${location.origin}${webhookUrl.value}`
  navigator.clipboard?.writeText(url).then(() => ElMessage.success('已复制'))
}

function applyDefinition(wf, usePositions = true) {
  meta.name = wf.name || ''
  meta.description = wf.description || ''
  meta.enabled = wf.enabled ?? false
  applyTrigger(wf.trigger)
  webhookUrl.value = wf.webhook_url || ''
  flowNodes.value = (wf.nodes || []).map((n, i) => ({
    id: n.id, type: 'wf',
    position: (usePositions && n.position) || layoutPosition(n, wf),
    data: {
      nodeType: n.type, typeName: nodeTypeOf(n.type)?.name || n.type,
      category: nodeTypeOf(n.type)?.category || '', name: n.name || nodeTypeOf(n.type)?.name || n.id,
      config: n.config || {}, on_error: n.on_error || null,
    },
  }))
  flowEdges.value = (wf.edges || []).map((e) => ({
    id: `e_${e.from}_${e.branch || 'x'}_${e.to}`,
    source: e.from, target: e.to,
    sourceHandle: e.branch || null, targetHandle: null,
    label: e.branch === 'true' ? '是' : e.branch === 'false' ? '否' : '',
    data: { branch: e.branch || null },
  }))
}

// AI 生成的定义没有坐标：按 DAG 深度分层布局
function layoutPosition(node, wf) {
  const edges = wf.edges || []
  const depth = (nid, seen = new Set()) => {
    if (seen.has(nid)) return 0
    seen.add(nid)
    const parents = edges.filter((e) => e.to === nid)
    if (!parents.length) return 0
    return 1 + Math.max(...parents.map((e) => depth(e.from, seen)))
  }
  const d = depth(node.id)
  const sameLayer = (wf.nodes || []).filter((n) => depth(n.id) === d)
  const idx = sameLayer.findIndex((n) => n.id === node.id)
  return { x: 80 + d * 240, y: 60 + idx * 110 }
}

function loadDraft() {
  let def = null
  try { def = JSON.parse(sessionStorage.getItem('grt_wf_draft') || 'null') } catch { def = null }
  if (!def?.nodes?.length) return
  sessionStorage.removeItem('grt_wf_draft')
  applyDefinition(def, false)
  if (def.notes) {
    ElMessageBox.alert(def.notes, 'AI 生成说明（请确认后保存）', { confirmButtonText: '知道了' })
  } else {
    ElMessage.success('AI 已生成工作流草稿，请确认后保存')
  }
}

onMounted(async () => {
  ;[tables.value, providers.value, nodeTypes.value] = await Promise.all([
    listTables(), listProviders(), workflowNodeTypes(),
  ])
  if (wfId.value) {
    const wf = await getWorkflow(wfId.value)
    applyDefinition(wf)
  } else if (route.query.draft) {
    loadDraft()
  }
})
</script>

<style scoped>
.wf-editor { height: 100vh; display: flex; flex-direction: column; background: #f5f7fa; }
.topbar {
  display: flex; align-items: center; gap: 12px; padding: 8px 16px;
  background: #fff; border-bottom: 1px solid #e4e7ed;
}
.name-input { width: 220px; }
.spacer { flex: 1; }
.body { flex: 1; display: flex; min-height: 0; }
.sidebar { width: 250px; background: #fff; border-right: 1px solid #e4e7ed; overflow-y: auto; padding: 12px; }
.side-section { margin-bottom: 18px; }
.side-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.mt { margin-top: 8px; }
.mb { margin-bottom: 10px; }
.row { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #606266; }
.hint { font-size: 12px; color: #909399; }
.webhook-url .hint { margin-bottom: 4px; }
.palette-cat { font-size: 12px; color: #909399; margin: 8px 0 4px; }
.palette-item {
  padding: 6px 10px; margin-bottom: 4px; border: 1px solid #e4e7ed; border-radius: 6px;
  cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 6px;
}
.palette-item:hover { border-color: #409eff; background: #ecf5ff; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #909399; }
.dot.cat-data { background: #409eff; }
.dot.cat-ai { background: #9b59b6; }
.dot.cat-logic { background: #e6a23c; }
.dot.cat-action { background: #67c23a; }
.dot.cat-human { background: #f56c6c; }
.canvas-wrap { flex: 1; min-width: 0; position: relative; }
.canvas { width: 100%; height: 100%; }
.empty-hint {
  position: absolute; top: 40%; left: 50%; transform: translateX(-50%);
  color: #c0c4cc; font-size: 14px; pointer-events: none;
}
.config-panel { width: 440px; flex-shrink: 0; background: #fff; border-left: 1px solid #e4e7ed; overflow-y: auto; padding: 12px; }
.config-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.config-title { font-size: 13px; font-weight: 600; }
</style>
