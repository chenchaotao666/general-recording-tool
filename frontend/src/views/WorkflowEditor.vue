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
      <el-button :disabled="!canUndo" title="撤销（Ctrl+Z）" @click="undo">撤销</el-button>
      <el-button :disabled="!canRedo" title="重做（Ctrl+Y）" @click="redo">重做</el-button>
      <el-button @click="tidyUp">整理画布</el-button>
      <el-button :loading="checking" @click="runCheck(true)">检查问题</el-button>
      <el-button v-if="wfId" @click="openRuns">执行日志</el-button>
      <el-button v-if="wfId" :loading="explaining" @click="explain">流程解读</el-button>
      <el-button v-if="wfId" :loading="running" @click="doRun(false)">立即执行</el-button>
      <el-button v-if="wfId" :loading="running" title="沙盒试运行：发通知/HTTP/写表/审批/延迟/子流程只模拟，不真实生效" @click="doRun(true)">试运行</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </div>

    <div class="body">
      <!-- 左侧：节点面板（可点击或拖拽入画布） -->
      <div class="sidebar">
        <div class="side-section palette">
          <div class="side-title">节点（点击或拖入画布）</div>
          <div v-for="[cat, items] in paletteGroups" :key="cat" class="palette-group">
            <div class="palette-cat">{{ CAT_NAMES[cat] || cat }}</div>
            <div v-for="nt in items" :key="nt.type" class="palette-item" :title="nt.description" draggable="true"
              @click="addNode(nt)" @dragstart="onPaletteDragstart($event, nt)">
              <span class="dot" :class="`cat-${nt.category}`" />{{ nt.name }}
            </div>
          </div>
        </div>
      </div>

      <!-- 画布 -->
      <div class="canvas-wrap" @dragover.prevent @drop="onPaletteDrop">
        <VueFlow v-model:nodes="flowNodes" v-model:edges="flowEdges" class="canvas" :delete-key-code="['Backspace', 'Delete']"
          :min-zoom="0.3" :max-zoom="1.6" @init="onVfInit" @connect="onConnect" @node-click="onNodeClick"
          @node-drag-stop="commitHistory" @pane-click="selectedId = null" @edge-click="selectedId = null">
          <Background pattern-color="#d4d7de" :gap="16" />
          <Controls />
          <MiniMap pannable zoomable />
          <template #node-wf="props">
            <FlowNode v-bind="props" />
          </template>
          <div v-if="flowNodes.length <= 1" class="empty-hint">从左侧点击或拖入节点到画布，把「触发器」和节点连线串联流程</div>
        </VueFlow>
      </div>

      <!-- 右侧：触发器 / 节点配置 -->
      <div v-if="selectedNode" class="config-panel" :style="{ width: panelWidth + 'px' }">
        <div class="panel-resizer" title="拖动调整宽度" @mousedown="startResize" />
        <!-- 保存前体检标注到当前节点的问题（错误红 / 建议黄） -->
        <template v-if="selectedNode.data.issues?.length">
          <el-alert v-for="(it, i) in selectedNode.data.issues" :key="i" :title="it.message"
            :type="it.level === 'error' ? 'error' : 'warning'" :closable="false" show-icon class="mb" />
        </template>
        <template v-if="selectedNode.id === TRIGGER_ID">
          <div class="config-head">
            <span class="config-title">触发器</span>
          </div>
          <TriggerForm :trigger="trigger" :tables="tables" :trigger-fields="triggerFields" :webhook-url="webhookUrl"
            :form-url="formUrl"
            v-model:description="meta.description" @table-change="loadTriggerFields" @copy-webhook="copyWebhook"
            @copy-form="copyFormLink" />
        </template>
        <template v-else>
          <div class="config-head">
            <span class="config-title">{{ selectedNode.data.typeName }} · {{ selectedNode.id }}</span>
            <div>
              <el-button link type="primary" size="small" @click="aiNodeVisible = true">AI 帮我配置</el-button>
              <el-button link type="danger" size="small" @click="removeNode(selectedNode.id)">删除节点</el-button>
            </div>
          </div>
          <el-input :model-value="selectedNode.data.name" placeholder="节点显示名" size="small" class="mb"
            @update:model-value="patchSelected({ name: $event })" />
          <!-- 节点级示例配置：配置为空且有示例时提供「照改」起点 -->
          <div v-if="exampleOfSelected" class="example-row">
            <el-button size="small" plain type="primary" @click="applyExample">填入示例配置</el-button>
            <span class="hint">照着一个能用的例子改，比从零配快</span>
          </div>
          <SchemaForm :schema="nodeTypeOf(selectedNode.data.nodeType)?.config_schema" :model-value="selectedNode.data.config"
            :tables="tables" :providers="providers" :fallback-table-id="fallbackTableId" :vars="upstreamVars"
            :record-fields="recordRuleFields"
            :node-type="selectedNode.data.nodeType" :node-id="selectedNode.id" :workflows="subWorkflowOptions"
            @update:model-value="patchSelected({ config: $event })" />
          <el-divider content-position="left">失败处理</el-divider>
          <el-select :model-value="selectedNode.data.on_error?.policy || 'stop'" size="small" style="width: 100%"
            @update:model-value="patchSelected({ on_error: { policy: $event, max_attempts: 3, backoff_seconds: 60 } })">
            <el-option label="终止流程（默认）" value="stop" />
            <el-option label="跳过该节点继续" value="continue" />
            <el-option label="自动重试（最多 3 次）" value="retry" />
          </el-select>

          <!-- 最近一次试运行回显：状态 + 耗时 + 输入/输出摘要（改配置后自动清除，避免误导） -->
          <template v-if="selectedNode.data.runState">
            <el-divider content-position="left">最近运行</el-divider>
            <div class="run-echo">
              <div class="run-echo-head">
                <el-tag size="small" :type="RUN_STATUS_TYPES[selectedNode.data.runState.status] || 'info'">
                  {{ RUN_STATUS_LABELS[selectedNode.data.runState.status] || selectedNode.data.runState.status }}
                </el-tag>
                <el-tag v-if="selectedNode.data.runState.output?.simulated" size="small" type="info" effect="plain">模拟</el-tag>
                <span class="hint">{{ selectedNode.data.runState.duration_ms }}ms</span>
              </div>
              <div v-if="selectedNode.data.runState.error" class="run-echo-err">{{ selectedNode.data.runState.error }}</div>
              <el-alert v-for="(w, i) in selectedNode.data.runState.warnings || []" :key="i" :title="w"
                type="warning" :closable="false" show-icon class="run-echo-warn" />
              <el-collapse class="run-echo-io">
                <el-collapse-item title="输入（渲染后配置）" name="in">
                  <JsonTree :data="selectedNode.data.runState.input" />
                </el-collapse-item>
                <el-collapse-item title="输出" name="out">
                  <JsonTree :data="selectedNode.data.runState.output" />
                </el-collapse-item>
              </el-collapse>
            </div>
          </template>
        </template>
      </div>
    </div>

    <!-- 执行日志抽屉：编辑器内直接看历史执行，不用退回列表页 -->
    <el-drawer v-model="runsVisible" title="执行日志" size="720px">
      <el-table :data="runs" size="small" v-loading="runsLoading">
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
            <el-tag :type="RUN_STATUS_TYPES[row.status] || 'info'" size="small">{{ RUN_STATUS_LABELS[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="token" width="70" align="right">
          <template #default="{ row }">{{ row.tokens_used || '' }}</template>
        </el-table-column>
        <el-table-column label="错误">
          <template #default="{ row }"><span class="run-err">{{ row.error }}</span></template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!runsLoading && !runs.length" description="暂无执行记录" />
    </el-drawer>

    <!-- AI 帮我配这个节点 -->
    <el-dialog v-model="aiNodeVisible" :title="`AI 配置 · ${selectedNode?.data.typeName || ''}`" width="480px">
      <el-input v-model="aiNodeDesc" type="textarea" :rows="4"
        placeholder="用一句话描述你想要的效果，例如：筛选过去 7 天金额大于 1000 的记录" />
      <template #footer>
        <el-button @click="aiNodeVisible = false">取消</el-button>
        <el-button type="primary" :loading="aiNodeLoading" @click="applyAiNodeConfig">生成并填入</el-button>
      </template>
    </el-dialog>

    <!-- AI 流程解读 -->
    <el-dialog v-model="explainVisible" title="这个流程在干什么（AI 解读）" width="520px">
      <div v-loading="explaining" class="explain-text">{{ explainText }}</div>
    </el-dialog>

    <!-- 问题清单：体检结果汇总，点击定位到对应节点 -->
    <el-drawer v-model="showIssues" title="问题检查" size="400px">
      <el-empty v-if="!issues.length" description="没有发现问题" />
      <div v-for="(it, i) in issues" :key="i" class="issue-item" @click="locateIssue(it)">
        <el-tag :type="it.level === 'error' ? 'danger' : 'warning'" size="small" effect="light" class="issue-tag">
          {{ it.level === 'error' ? '错误' : '建议' }}
        </el-tag>
        <div class="issue-body">
          <div class="issue-node">{{ nodeLabel(it.node_id) }}</div>
          <div class="issue-msg">{{ it.message }}</div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import {
  aiExplainWorkflow, aiNodeConfig, checkWorkflow, createWorkflow, getTable, getWorkflow, getWorkflowRun,
  listProviders, listTables, listWorkflows,
  runWorkflow, testRunWorkflow, updateWorkflow, workflowNodeTypes, workflowRuns,
} from '../api'
import FlowNode from '../components/workflow/FlowNode.vue'
import SchemaForm from '../components/workflow/SchemaForm.vue'
import TriggerForm from '../components/workflow/TriggerForm.vue'
import JsonTree from '../components/workflow/JsonTree.vue'

const CAT_NAMES = { data: '数据', ai: 'AI', logic: '逻辑', action: '动作', human: '人工' }

// 触发器节点：画布上固定一个（不可删除、只有出口），保存时剥离成后端 {trigger} 结构
const TRIGGER_ID = 'trigger'
const TRIGGER_TYPE_NAMES = {
  manual: '被动调用', schedule: '定时触发', record_created: '记录新增时',
  record_updated: '记录修改时', webhook: 'Webhook 回调', form: '表单提交',
}
// 分支出边的中文标签（边的 branch 值 → 画布标签）
const BRANCH_LABELS = { true: '是', false: '否', loop: '每条', done: '完成' }
// 试运行回显的状态文案/颜色（画布节点角标 + 配置面板「最近运行」共用）
const RUN_STATUS_LABELS = { success: '成功', failed: '失败', waiting: '等待中', skipped: '已跳过', running: '执行中', pending: '排队中', cancelled: '已取消' }
const RUN_STATUS_TYPES = { success: 'success', failed: 'danger', waiting: 'warning', skipped: 'info', running: 'primary', pending: 'info', cancelled: 'info' }
// 执行日志抽屉的触发方式文案（后端 run.trigger 值）
const TRIGGER_LABELS = { manual: '手动', schedule: '定时', record: '数据变更', webhook: 'Webhook', test: '试运行', form: '表单', sub: '子流程' }

const route = useRoute()
const router = useRouter()
const wfId = ref(route.params.id ? Number(route.params.id) : null)

const meta = reactive({ name: '', description: '', enabled: false })
const trigger = reactive({ type: 'manual', sched_kind: 'interval', minutes: 60, expr: '0 9 * * *', table_id: null, watch_fields: [], secret: '', response_template: '' })
const webhookUrl = ref('')
const formUrl = ref('')
const tables = ref([])
const providers = ref([])
const nodeTypes = ref([])
const triggerFields = ref([])
const allWorkflows = ref([])   // 子流程调用节点的下拉数据源
// 子流程候选：排除自己，且只能是「仅手动运行」的流程（被调用的流程不应有自己的自动触发器）
const subWorkflowOptions = computed(() =>
  allWorkflows.value.filter((w) => w.id !== wfId.value && (w.trigger?.type || 'manual') === 'manual')
)

const flowNodes = ref([])
const flowEdges = ref([])
const selectedId = ref(null)
const vfInstance = ref(null)   // Vue Flow store 实例（@init 载荷）
let pendingFit = false
let pendingFocus = null   // ?node=xxx：从运行详情跳入时，节点量完尺寸后选中并居中
// 节点是异步渲染的，fitView 必须等全部节点量完尺寸（onNodesInitialized），
// 否则只量好一部分节点时就 fit，画布只能显示左半截
function onVfInit(inst) {
  vfInstance.value = inst
  inst.onNodesInitialized?.(() => {
    if (pendingFocus) {
      const n = flowNodes.value.find((x) => x.id === pendingFocus)
      pendingFocus = null
      if (n) focusCanvasNode(n)
      return
    }
    if (!pendingFit) return
    pendingFit = false
    inst.fitView({ padding: 0.15 })
  })
}

// 定位到画布节点：选中（vue-flow 选中态 + 打开配置面板）并居中
function focusCanvasNode(n) {
  flowNodes.value.forEach((x) => { x.selected = x.id === n.id })
  selectedId.value = n.id
  vfInstance.value?.setCenter(n.position.x + 80, n.position.y + 40, { zoom: 1, duration: 300 })
}
function fitCanvas() { pendingFit = true }
const saving = ref(false)
const running = ref(false)
const idCounters = {}

const selectedNode = computed(() => flowNodes.value.find((n) => n.id === selectedId.value))

// ---- 撤销/重做：快照栈（栈顶 = 当前状态）----
// 结构变化（增删节点/连线，含键盘 Delete）由 sync watch 捕获；拖动在 drag-stop 提交；
// 文本编辑（patchSelected）防抖合并，避免每个 keystroke 一条历史
const histStack = ref([])
const histIndex = ref(-1)
let restoring = false
let histTimer = null

function snapshot() {
  // JSON 化同时剥离 data.onAction 函数引用；恢复时再挂回
  return JSON.stringify({ nodes: flowNodes.value, edges: flowEdges.value })
}

function commitHistory() {
  if (restoring) return
  const s = snapshot()
  if (histStack.value[histIndex.value] === s) return   // 无变化不压栈
  histStack.value = [...histStack.value.slice(0, histIndex.value + 1), s].slice(-50)
  histIndex.value = histStack.value.length - 1
}

function commitHistoryDebounced() {
  clearTimeout(histTimer)
  histTimer = setTimeout(commitHistory, 800)
}

function flushHistory() {   // 撤销/重做前先落掉防抖中的编辑，保证栈顶是当前画布
  clearTimeout(histTimer)
  histTimer = null
  commitHistory()
}

const canUndo = computed(() => histIndex.value > 0)
const canRedo = computed(() => histIndex.value >= 0 && histIndex.value < histStack.value.length - 1)

function restore(s) {
  restoring = true
  try {
    const parsed = JSON.parse(s)
    parsed.nodes.forEach((n) => { n.data.onAction = nodeAction })
    flowNodes.value = parsed.nodes
    flowEdges.value = parsed.edges
    if (selectedId.value && !parsed.nodes.some((n) => n.id === selectedId.value)) selectedId.value = null
  } finally {
    restoring = false
  }
}

function undo() {
  flushHistory()
  if (!canUndo.value) return
  histIndex.value -= 1
  restore(histStack.value[histIndex.value])
}

function redo() {
  flushHistory()
  if (!canRedo.value) return
  histIndex.value += 1
  restore(histStack.value[histIndex.value])
}

// 结构变化（节点/连线数量变化：添加、删除、连线、键盘 Delete）→ 提交历史。
// flush:sync 保证 restore 期间 restoring 标记仍生效（同步触发），不会把恢复当成新编辑
watch([() => flowNodes.value.length, () => flowEdges.value.length], () => commitHistory(), { flush: 'sync' })

function onEditorKeydown(e) {
  if (!(e.ctrlKey || e.metaKey)) return
  const el = document.activeElement
  if (el && (['INPUT', 'TEXTAREA'].includes(el.tagName) || el.isContentEditable)) return   // 不抢输入框的撤销
  const k = e.key.toLowerCase()
  if (k === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo() }
  else if (k === 'y') { e.preventDefault(); redo() }
}

// ---- 保存前体检（lint）：问题标注到画布节点 + 清单抽屉 ----
const issues = ref([])
const showIssues = ref(false)
const checking = ref(false)

function setIssues(list) {
  issues.value = list || []
  const byNode = {}
  for (const it of issues.value) (byNode[it.node_id || ''] ||= []).push(it)
  for (const n of flowNodes.value) n.data.issues = byNode[n.id] || []
}

async function runCheck(showOk = false) {
  checking.value = true
  try {
    const r = await checkWorkflow(buildPayload())
    setIssues(r.issues || [])
    if (issues.value.length) showIssues.value = true
    else if (showOk) ElMessage.success('没有发现问题')
    return issues.value
  } catch (e) {
    ElMessage.error(e.message)
    return null
  } finally {
    checking.value = false
  }
}

function nodeLabel(id) {
  if (id === TRIGGER_ID) return '触发器'
  const n = flowNodes.value.find((x) => x.id === id)
  return n ? `${n.data.name}（${id}）` : '流程结构'
}

function locateIssue(it) {
  if (!it.node_id) return
  const n = flowNodes.value.find((x) => x.id === it.node_id)
  if (n) focusCanvasNode(n)
}

// ---- AI 帮我配这个节点 ----
const aiNodeVisible = ref(false)
const aiNodeDesc = ref('')
const aiNodeLoading = ref(false)

async function applyAiNodeConfig() {
  const n = selectedNode.value
  if (!n) return
  if (!aiNodeDesc.value.trim()) { ElMessage.warning('请描述你想要的配置'); return }
  aiNodeLoading.value = true
  try {
    const r = await aiNodeConfig(n.data.nodeType, aiNodeDesc.value.trim())
    patchSelected({ config: { ...(n.data.config || {}), ...(r.config || {}) } })
    aiNodeVisible.value = false
    aiNodeDesc.value = ''
    ElMessage.success('已填入 AI 生成的配置，请检查确认后保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiNodeLoading.value = false
  }
}

// ---- AI 流程解读 ----
const explainVisible = ref(false)
const explainText = ref('')
const explaining = ref(false)

async function explain() {
  explainVisible.value = true
  explainText.value = ''
  explaining.value = true
  try {
    const r = await aiExplainWorkflow(wfId.value)
    explainText.value = r.explanation || '（没有解读内容）'
  } catch (e) {
    explainVisible.value = false
    ElMessage.error(e.message)
  } finally {
    explaining.value = false
  }
}

// ---- 执行日志抽屉 ----
const runsVisible = ref(false)
const runs = ref([])
const runsLoading = ref(false)

async function openRuns() {
  runsVisible.value = true
  runsLoading.value = true
  try { runs.value = await workflowRuns(wfId.value) }
  catch (e) { ElMessage.error(e.message) }
  finally { runsLoading.value = false }
}

function makeTriggerNode(position) {
  return {
    id: TRIGGER_ID, type: 'wf', position, deletable: false,
    data: {
      nodeType: 'trigger', typeName: '触发器', category: 'trigger',
      name: TRIGGER_TYPE_NAMES[trigger.type] || '触发器', config: {}, on_error: null,
    },
  }
}
// 触发器类型变化时同步节点显示名
watch(() => trigger.type, () => {
  const n = flowNodes.value.find((x) => x.id === TRIGGER_ID)
  if (n) n.data.name = TRIGGER_TYPE_NAMES[trigger.type] || '触发器'
})

// 选中节点自身没有 table_id 时（如条件分支），沿上游边找最近的数据表，
// 兜底用触发器监听的表——给筛选条件/字段选择器提供字段清单，字段才能显示中文名
const fallbackTableId = computed(() => {
  const n = selectedNode.value
  if (!n || n.data.config?.table_id) return null
  const parentsOf = (id) => flowEdges.value.filter((e) => e.target === id).map((e) => e.source)
  const queue = parentsOf(n.id)
  const seen = new Set([n.id])
  while (queue.length) {
    const nid = queue.shift()
    if (seen.has(nid)) continue
    seen.add(nid)
    const tid = flowNodes.value.find((x) => x.id === nid)?.data?.config?.table_id
    if (tid) return tid
    queue.push(...parentsOf(nid))
  }
  return trigger.table_id || null
})

// 右侧配置面板宽度：可拖动调整，记忆到 localStorage
const panelWidth = ref(Number(localStorage.getItem('grt_wf_panel_w')) || 520)
function startResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startW = panelWidth.value
  const onMove = (ev) => {
    panelWidth.value = Math.min(860, Math.max(380, startW + (startX - ev.clientX)))
  }
  const onUp = () => {
    localStorage.setItem('grt_wf_panel_w', String(panelWidth.value))
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// ---- 模板变量：选中节点的上游输出 + 触发器，供「插入变量」面板使用 ----
// 每种节点类型的输出变量生成器；(node, 该节点数据表的字段清单) => [{label, expr}]
const OUTPUT_VARS = {
  query_records: (n, fields) => [
    { label: '记录数', expr: `{nodes.${n.id}.count}` },
    { label: '记录列表', expr: `{nodes.${n.id}.records}` },
    { label: '第一条·ID', expr: `{nodes.${n.id}.records.0.id}` },
    ...fields.map((f) => ({ label: `第一条·${f.label}`, expr: `{nodes.${n.id}.records.0.${f.field_name}}` })),
  ],
  create_record: (n, fields) => [
    { label: '新记录（整体）', expr: `{nodes.${n.id}.record}` },
    { label: '新记录·ID', expr: `{nodes.${n.id}.record.id}` },
    ...fields.map((f) => ({ label: `新记录·${f.label}`, expr: `{nodes.${n.id}.record.${f.field_name}}` })),
  ],
  update_record: (n) => [
    { label: '更新条数', expr: `{nodes.${n.id}.count}` },
    { label: '更新后的记录', expr: `{nodes.${n.id}.records}` },
  ],
  llm_transform: (n) => {
    // 填了「JSON 输出键名」就展开成完整路径，不用再手改「键名」占位符
    const keys = (n.data.config?.output_keys || []).filter((k) => typeof k === 'string' && k.trim())
    return [
      { label: 'AI 文本输出', expr: `{nodes.${n.id}.text}` },
      ...(keys.length
        ? keys.map((k) => ({ label: `AI JSON·${k}`, expr: `{nodes.${n.id}.data.${k.trim()}}` }))
        : [{ label: 'AI JSON 输出·键名（需自行替换）', expr: `{nodes.${n.id}.data.键名}` }]),
    ]
  },
  condition: (n) => [{ label: '是否命中（true/false）', expr: `{nodes.${n.id}.matched}` }],
  switch: (n) => [{ label: '命中的分支名', expr: `{nodes.${n.id}.case}` }],
  foreach: (n, fields) => [
    { label: '当前条目（整体）', expr: `{nodes.${n.id}.item}` },
    // 能解析出列表来源表时展开真实字段（不用再手改「字段名」占位），否则保留占位项兜底
    ...(fields.length
      ? fields.map((f) => ({ label: `当前条目·${f.label}`, expr: `{nodes.${n.id}.item.${f.field_name}}` }))
      : [{ label: '当前条目·字段名（需自行替换）', expr: `{nodes.${n.id}.item.字段名}` }]),
    { label: '当前序号（从 0 起）', expr: `{nodes.${n.id}.index}` },
    { label: '总条数', expr: `{nodes.${n.id}.count}` },
  ],
  aggregate: (n) => [
    { label: '记录数', expr: `{nodes.${n.id}.count}` },
    { label: '统计结果（整体）', expr: `{nodes.${n.id}.stats}` },
    { label: '分组统计（整体）', expr: `{nodes.${n.id}.groups}` },
  ],
  dedupe: (n) => [
    { label: '去重后列表', expr: `{nodes.${n.id}.records}` },
    { label: '去重后条数', expr: `{nodes.${n.id}.count}` },
    { label: '去掉条数', expr: `{nodes.${n.id}.removed}` },
  ],
  sub_workflow: (n) => [
    { label: '执行状态', expr: `{nodes.${n.id}.status}` },
    { label: '运行 ID', expr: `{nodes.${n.id}.run_id}` },
  ],
  date_calc: (n) => [
    { label: '日期（YYYY-MM-DD）', expr: `{nodes.${n.id}.date}` },
    { label: '日期时间', expr: `{nodes.${n.id}.datetime}` },
  ],
  delay: (n) => [{ label: '等到的时间', expr: `{nodes.${n.id}.until}` }],
  approval: (n) => [
    { label: '审批结果（整体）', expr: `{nodes.${n.id}}` },   // 整体是 dict：{approved, comment, ...}，可直接作条件分支的判断对象
    { label: '是否通过', expr: `{nodes.${n.id}.approved}` },
    { label: '审批意见', expr: `{nodes.${n.id}.comment}` },
  ],
  send_message: (n) => [{ label: '发送人数', expr: `{nodes.${n.id}.sent}` }],
  http_request: (n) => [
    { label: 'HTTP 状态码', expr: `{nodes.${n.id}.status}` },
    { label: '响应内容', expr: `{nodes.${n.id}.body}` },
  ],
}

// 选中节点的全部上游（近 → 远）
const upstreamNodes = computed(() => {
  const n = selectedNode.value
  if (!n) return []
  const parentsOf = (id) => flowEdges.value.filter((e) => e.target === id).map((e) => e.source)
  const out = []
  const queue = parentsOf(n.id)
  const seen = new Set([n.id])
  while (queue.length) {
    const nid = queue.shift()
    if (seen.has(nid)) continue
    seen.add(nid)
    const anc = flowNodes.value.find((x) => x.id === nid)
    if (anc) out.push(anc)
    queue.push(...parentsOf(nid))
  }
  return out
})

// 上游节点数据表的字段清单（按需加载，供“第一条·字段名”展开）
const upFields = ref({})   // table_id -> MetaField[]
const upFieldsCache = new Map()
async function loadUpFields(tableId) {
  if (!tableId || upFields.value[tableId]) return
  if (!upFieldsCache.has(tableId)) {
    try { upFieldsCache.set(tableId, (await getTable(tableId)).fields || []) }
    catch { upFieldsCache.set(tableId, []) }
  }
  upFields.value = { ...upFields.value, [tableId]: upFieldsCache.get(tableId) }
}
watch(upstreamNodes, (list) => {
  for (const n of list) if (n.data.config?.table_id) loadUpFields(n.data.config.table_id)
}, { immediate: true })

// 内置时间变量（引擎每次执行实时计算）：定时/手动流程没有上游节点也能插入变量
const NOW_VARS = [
  { label: '今天', expr: '{now.today}' },
  { label: '昨天', expr: '{now.yesterday}' },
  { label: '明天', expr: '{now.tomorrow}' },
  { label: '现在（日期时间）', expr: '{now.datetime}' },
  { label: '本周一', expr: '{now.week_start}' },
  { label: '上周一', expr: '{now.last_week_start}' },
  { label: '上周日', expr: '{now.last_week_end}' },
  { label: '本月 1 日', expr: '{now.month_start}' },
  { label: '上月 1 日', expr: '{now.last_month_start}' },
  { label: '上月最后一日', expr: '{now.last_month_end}' },
]

// 逐条处理节点的「当前条目·字段」展开：从 items 表达式（{nodes.X.records}）找到来源节点，
// 用来源表的字段清单生成完整路径，用户不必再手改「字段名」占位符
function foreachItemFields(n) {
  const m = /^\{nodes\.([a-z0-9_]+)\.records\}$/.exec((n.data.config?.items || '').trim())
  const src = m && flowNodes.value.find((x) => x.id === m[1])
  const tid = src?.data?.config?.table_id
  return tid ? (upFields.value[tid] || []) : []
}

const upstreamVars = computed(() => {
  const groups = []
  if (trigger.type === 'record_created' || trigger.type === 'record_updated' || trigger.type === 'form') {
    groups.push({
      title: '触发器',
      items: [
        { label: '触发记录（整体）', expr: '{trigger.record}' },
        { label: '触发记录·ID', expr: '{trigger.record.id}' },
        ...triggerFields.value.map((f) => ({ label: `触发记录·${f.label}`, expr: `{trigger.record.${f.field_name}}` })),
        { label: '触发记录·创建时间', expr: '{trigger.record.created_at}' },
        { label: '触发记录·更新时间', expr: '{trigger.record.updated_at}' },
      ],
    })
  } else if (trigger.type === 'manual' || trigger.type === 'webhook') {
    groups.push({
      title: '触发器',
      items: [{ label: '触发参数·参数名（需自行替换）', expr: '{trigger.params.参数名}' }],
    })
  }
  for (const n of upstreamNodes.value) {
    const maker = OUTPUT_VARS[n.data.nodeType]
    if (!maker) continue
    const fields = n.data.nodeType === 'foreach'
      ? foreachItemFields(n)
      : (upFields.value[n.data.config?.table_id] || [])
    const items = maker(n, fields)
    if (items.length) groups.push({ title: `${n.data.name} (${n.id})`, items })
  }
  groups.push({ title: '时间变量（内置）', items: NOW_VARS, datePicker: true })   // 内置变量放最后，业务变量优先；datePicker = 分组顶部带具体日期选择器
  return groups
})
// 条件/多路分支的条件规则字段：**跟随判断对象**（record 配置），不是固定某张表——
// 判断对象是审批输出时字段就是 approved/comment，是触发记录时是触发表的字段
const recordRuleFields = computed(() => {
  const n = selectedNode.value
  if (!n || !['condition', 'switch'].includes(n.data.nodeType)) return null
  const rec = (n.data.config?.record || '').trim()
  // {trigger.record} / {trigger.old_record} → 触发器监听的表
  if (/^\{trigger\.(old_)?record\}$/.test(rec)) return triggerFields.value.length ? triggerFields.value : null
  // {nodes.x}（审批等节点的整体输出）→ 该节点输出键
  const whole = /^\{nodes\.([a-z0-9_]+)\}$/.exec(rec)
  if (whole) {
    const t = flowNodes.value.find((x) => x.id === whole[1])?.data?.nodeType
    if (t === 'approval') {
      return [
        { field_name: 'approved', label: '是否通过', data_type: 'bool' },
        { field_name: 'comment', label: '审批意见', data_type: 'varchar' },
        { field_name: 'approver_id', label: '审批人 ID', data_type: 'int' },
      ]
    }
    return null
  }
  // {nodes.x.record}（新增记录的整条输出）→ 该节点写的表
  const m = /^\{nodes\.([a-z0-9_]+)\.record\}$/.exec(rec)
  if (m) {
    const tid = flowNodes.value.find((x) => x.id === m[1])?.data?.config?.table_id
    const fs = tid ? (upFields.value[tid] || []) : []
    return fs.length ? fs : null
  }
  // {nodes.x.item}（循环当前条目）→ 循环列表来源表
  const it = /^\{nodes\.([a-z0-9_]+)\.item\}$/.exec(rec)
  if (it) {
    const fe = flowNodes.value.find((x) => x.id === it[1])
    const fs = fe ? foreachItemFields(fe) : []
    return fs.length ? fs : null
  }
  return null   // 自定义表达式：退回兜底表逻辑
})

const nodeTypeOf = (t) => nodeTypes.value.find((x) => x.type === t)
const paletteGroups = computed(() => {
  const groups = {}
  for (const nt of nodeTypes.value) (groups[nt.category] ||= []).push(nt)
  return Object.entries(groups)
})

// 点击添加的落点：视口中央偏上附近找第一个不重叠的空位（找不到就逐行下移），不再固定斜线叠加
function freeSpot() {
  let base = { x: 160, y: 100 }
  const wrap = document.querySelector('.canvas-wrap')
  if (vfInstance.value && wrap) {
    const r = wrap.getBoundingClientRect()
    base = vfInstance.value.screenToFlowCoordinate({ x: r.left + r.width / 2, y: r.top + r.height / 3 })
  }
  let { x, y } = base
  for (let i = 0; i < 60; i++) {
    const hit = flowNodes.value.some((n) => Math.abs(n.position.x - x) < 180 && Math.abs(n.position.y - y) < 90)
    if (!hit) break
    y += 100
  }
  return { x: Math.round(x - 80), y: Math.round(y - 30) }   // 中心点换算为节点左上角
}

function addNode(nt, position = null) {
  idCounters[nt.type] = (idCounters[nt.type] || 0) + 1
  let id = `${nt.type.split('_')[0]}_${idCounters[nt.type]}`
  while (flowNodes.value.some((n) => n.id === id)) id = `${id}x`
  flowNodes.value.push({
    id, type: 'wf',
    position: position || freeSpot(),
    data: { nodeType: nt.type, typeName: nt.name, category: nt.category, name: nt.name, config: {}, on_error: null, disabled: false, onAction: nodeAction },
  })
  selectedId.value = id   // 自动打开配置面板
  focusFirstField()
}

// 添加/复制节点后聚焦配置面板第一个输入框，形成「加节点 → 立即配置」的引导流
function focusFirstField() {
  nextTick(() => {
    document.querySelector('.config-panel input:not([type=checkbox]):not([readonly]), .config-panel textarea')?.focus()
  })
}

// 节点面板拖拽入画布：dragstart 带上节点类型，drop 时按鼠标位置落点
function onPaletteDragstart(e, nt) {
  e.dataTransfer.setData('application/grt-node-type', nt.type)
  e.dataTransfer.effectAllowed = 'move'
}

function onPaletteDrop(e) {
  const t = e.dataTransfer.getData('application/grt-node-type')
  const nt = nodeTypes.value.find((x) => x.type === t)
  if (!nt || !vfInstance.value) return
  const pos = vfInstance.value.screenToFlowCoordinate({ x: e.clientX, y: e.clientY })
  addNode(nt, { x: Math.round(pos.x - 80), y: Math.round(pos.y - 30) })
}

function onConnect(params) {
  if (params.target === TRIGGER_ID) return   // 触发器没有入口
  const srcType = flowNodes.value.find((n) => n.id === params.source)?.data?.nodeType
  // 条件分支出边带 true/false；多路分支带分支名/default；逐条处理带 loop/done
  const branch = ['condition', 'switch', 'foreach'].includes(srcType) && params.sourceHandle ? params.sourceHandle : null
  if (flowEdges.value.some((e) => e.source === params.source && e.target === params.target && (e.data?.branch || null) === branch)) return
  flowEdges.value.push({
    id: `e_${params.source}_${branch || 'x'}_${params.target}`,
    source: params.source, target: params.target,
    sourceHandle: params.sourceHandle, targetHandle: params.targetHandle,
    label: BRANCH_LABELS[branch] || branch || '',
    data: { branch },
  })
}

function onNodeClick({ node }) { selectedId.value = node.id }

// ---- 节点悬停工具栏动作：试运行到此 / 停用 / 复制 / 删除 ----
function nodeAction(action, id) {
  if (action === 'delete') return removeNode(id)
  if (action === 'duplicate') return duplicateNode(id)
  if (action === 'toggle-disabled') {
    const n = flowNodes.value.find((x) => x.id === id)
    if (n) n.data.disabled = !n.data.disabled
    return
  }
  if (action === 'run-to') return runToNode(id)
}

function duplicateNode(id) {
  const src = flowNodes.value.find((x) => x.id === id)
  if (!src || id === TRIGGER_ID) return
  const t = src.data.nodeType
  idCounters[t] = (idCounters[t] || 0) + 1
  let nid = `${t.split('_')[0]}_${idCounters[t]}`
  while (flowNodes.value.some((n) => n.id === nid)) nid = `${nid}x`
  const data = JSON.parse(JSON.stringify({ ...src.data, onAction: undefined }))  // 深拷贝配置（函数不入 JSON）
  data.onAction = nodeAction
  data.name = `${src.data.name} 副本`
  flowNodes.value.push({
    id: nid, type: 'wf',
    position: { x: src.position.x + 40, y: src.position.y + 60 },
    data,
  })
  selectedId.value = nid
}

// 整理画布：按 DAG 深度分层重排（层内保持当前的上下顺序）
function tidyUp() {
  const depthCache = {}
  const depth = (nid, seen = new Set()) => {
    if (depthCache[nid] !== undefined) return depthCache[nid]
    if (seen.has(nid)) return 0
    seen.add(nid)
    const parents = flowEdges.value.filter((e) => e.target === nid)
    const d = parents.length ? 1 + Math.max(...parents.map((e) => depth(e.source, seen))) : 0
    depthCache[nid] = d
    return d
  }
  const layers = {}
  for (const n of flowNodes.value) (layers[depth(n.id)] ||= []).push(n)
  for (const [d, list] of Object.entries(layers)) {
    list.sort((a, b) => a.position.y - b.position.y)
    list.forEach((n, i) => { n.position = { x: 80 + Number(d) * 240, y: 60 + i * 110 } })
  }
  // 位置变化不需要重新量尺寸，直接 fit
  commitHistory()
  nextTick(() => vfInstance.value?.fitView({ padding: 0.15 }))
}

// ---- 试运行结果回显画布：节点状态角标 + 配置面板「最近运行」摘要 ----
async function echoRunToCanvas(runId) {
  try {
    const detail = await getWorkflowRun(runId)
    const byNode = {}
    for (const nr of detail.node_runs || []) byNode[nr.node_id] = nr   // 重试/循环取最后一次
    for (const n of flowNodes.value) {
      const nr = byNode[n.id]
      n.data.runState = nr
        ? { status: nr.status, duration_ms: nr.duration_ms, error: nr.error, warnings: nr.warnings || [], input: nr.input, output: nr.output }
        : (n.id === TRIGGER_ID ? n.data.runState : null)
    }
  } catch { /* 回显失败不影响执行结果展示 */ }
}

// 单节点试运行：真实执行到该节点为止（需先保存）
async function runToNode(id) {
  if (!wfId.value) { ElMessage.warning('请先保存工作流，再试运行'); return }
  const n = flowNodes.value.find((x) => x.id === id)
  running.value = true
  try {
    const r = await testRunWorkflow(wfId.value, {}, id)
    await echoRunToCanvas(r.id)
    const ok = r.status === 'success'
    ElMessageBox({
      title: ok ? '试运行完成' : '试运行未成功',
      message: `已执行到「${n?.data.name || id}」：状态 ${r.status}${r.error ? `；${r.error}` : ''}；消耗 token：${r.tokens_used}。（沙盒试运行：副作用节点均为模拟，未真实生效）`,
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

function patchSelected(patch) {
  const n = flowNodes.value.find((x) => x.id === selectedId.value)
  if (n) {
    Object.assign(n.data, patch)
    n.data.runState = null   // 配置变了，上次运行回显即过期，避免误导
  }
  commitHistoryDebounced()
}

// 节点级示例配置：配置为空且节点目录带 example_config 时，给「照改」起点。
// 注意"为空"的判定：SchemaForm 打开面板会自动回填 schema 默认值（limit=100 等），
// 只含默认值/空值的配置仍视为空——否则按钮在面板打开的瞬间就被默认值顶掉了
const exampleOfSelected = computed(() => {
  const n = selectedNode.value
  if (!n || n.id === TRIGGER_ID) return null
  const nt = nodeTypeOf(n.data.nodeType)
  if (!nt?.example_config) return null
  const props = nt.config_schema?.properties || {}
  const meaningful = Object.entries(n.data.config || {}).filter(([k, v]) => {
    if (v === undefined || v === null || v === '') return false
    if (props[k]?.default !== undefined && v === props[k].default) return false   // 自动回填的默认值不算
    return true
  })
  return meaningful.length ? null : nt.example_config
})

function applyExample() {
  if (!exampleOfSelected.value) return
  patchSelected({ config: JSON.parse(JSON.stringify(exampleOfSelected.value)) })
  ElMessage.success('已填入示例配置，按需修改后保存')
}

async function removeNode(id) {
  if (id === TRIGGER_ID) return   // 触发器节点不可删除
  const n = flowNodes.value.find((x) => x.id === id)
  try {
    await ElMessageBox.confirm(`删除节点「${n?.data.name || id}」及其连线？（误删可用 Ctrl+Z 撤销）`, '删除节点',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  flowNodes.value = flowNodes.value.filter((x) => x.id !== id)
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
  if (t.type === 'webhook') return { type: 'webhook', secret: t.secret || undefined, response_template: t.response_template || undefined }
  if (t.type === 'form') return { type: 'form', table_id: t.table_id, secret: t.secret || undefined }
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
  trigger.response_template = t.response_template || ''
  if (trigger.table_id) loadTriggerFields()
}

function buildPayload() {
  return {
    name: meta.name.trim(),
    description: meta.description,
    enabled: meta.enabled,
    trigger: buildTrigger(),
    // 触发器节点及其出边只存在于画布，不落库（后端仍是 {trigger, nodes, edges} 结构）
    nodes: flowNodes.value.filter((n) => n.id !== TRIGGER_ID).map((n) => ({
      id: n.id, type: n.data.nodeType, name: n.data.name,
      config: n.data.config || {}, on_error: n.data.on_error || undefined,
      disabled: n.data.disabled || undefined,
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
    })),
    edges: flowEdges.value.filter((e) => e.source !== TRIGGER_ID && e.target !== TRIGGER_ID).map((e) => ({
      from: e.source, to: e.target, ...(e.data?.branch ? { branch: e.data.branch } : {}),
    })),
  }
}

async function save() {
  if (!meta.name.trim()) { ElMessage.warning('请填写工作流名称'); return }
  saving.value = true
  try {
    // 保存前体检：错误阻断保存并标注到画布；建议级不阻断
    const list = await runCheck()
    if (list === null) return   // 体检请求失败（已提示），不继续保存
    const errs = list.filter((i) => i.level === 'error')
    if (errs.length) {
      ElMessage.error(`有 ${errs.length} 个错误需要处理（已标注在画布上，点「检查问题」查看清单）`)
      return
    }
    const payload = buildPayload()
    const saved = wfId.value
      ? await updateWorkflow(wfId.value, payload)
      : await createWorkflow(payload)
    wfId.value = saved.id
    webhookUrl.value = saved.webhook_url || ''
    formUrl.value = saved.form_url || ''
    if (saved.trigger?.secret) trigger.secret = saved.trigger.secret
    if (list.length) ElMessage.warning(`已保存，还有 ${list.length} 个建议处理的问题（见问题清单）`)
    else ElMessage.success('已保存')
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
    await echoRunToCanvas(r.id)
    const ok = r.status === 'success'
    ElMessageBox({
      title: ok ? '执行完成' : '执行未成功',
      message: `状态：${r.status}${r.error ? `；${r.error}` : ''}；消耗 token：${r.tokens_used}`
        + (isTest ? '。（沙盒试运行：副作用节点均为模拟，未真实生效）' : ''),
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

function copyFormLink() {
  const url = `${location.origin}${formUrl.value}`
  navigator.clipboard?.writeText(url).then(() => ElMessage.success('已复制'))
}

function applyDefinition(wf, usePositions = true) {
  meta.name = wf.name || ''
  meta.description = wf.description || ''
  meta.enabled = wf.enabled ?? false
  applyTrigger(wf.trigger)
  webhookUrl.value = wf.webhook_url || ''
  formUrl.value = wf.form_url || ''

  const realNodes = wf.nodes || []
  const baseEdges = wf.edges || []
  const hasIncoming = new Set(baseEdges.map((e) => e.to))
  // 触发器节点 → 没有入边的起始节点（后端不存触发器的边，画布上合成）
  const allEdges = [...baseEdges, ...realNodes.filter((n) => !hasIncoming.has(n.id)).map((n) => ({ from: TRIGGER_ID, to: n.id }))]

  // 坐标：已保存的用原坐标；AI 草稿按 DAG 深度分层（触发器是第 0 层）
  const depthCache = {}
  const depth = (nid, seen = new Set()) => {
    if (depthCache[nid] !== undefined) return depthCache[nid]
    if (seen.has(nid)) return 0
    seen.add(nid)
    const parents = allEdges.filter((e) => e.to === nid)
    const d = parents.length ? 1 + Math.max(...parents.map((e) => depth(e.from, seen))) : 0
    depthCache[nid] = d
    return d
  }
  const posOf = (n) => {
    if (usePositions && n.position) return n.position
    const d = depth(n.id)
    const idx = realNodes.filter((x) => depth(x.id) === d).findIndex((x) => x.id === n.id)
    return { x: 80 + d * 240, y: 60 + idx * 110 }
  }
  const triggerPos = (() => {
    if (!realNodes.length) return { x: 80, y: 120 }
    if (usePositions && realNodes.some((n) => n.position)) {
      const xs = realNodes.map((n) => n.position?.x ?? 80)
      const starts = realNodes.filter((n) => !hasIncoming.has(n.id))
      const ys = starts.map((n) => n.position?.y ?? 120)
      return { x: Math.min(...xs) - 240, y: Math.round(ys.reduce((a, b) => a + b, 0) / ys.length) }
    }
    return { x: 80, y: 60 }
  })()

  flowNodes.value = [
    makeTriggerNode(triggerPos),
    ...realNodes.map((n) => ({
      id: n.id, type: 'wf',
      position: posOf(n),
      data: {
        nodeType: n.type, typeName: nodeTypeOf(n.type)?.name || n.type,
        category: nodeTypeOf(n.type)?.category || '', name: n.name || nodeTypeOf(n.type)?.name || n.id,
        config: n.config || {}, on_error: n.on_error || null,
        disabled: n.disabled || false, onAction: nodeAction,
      },
    })),
  ]
  flowEdges.value = allEdges.map((e) => ({
    id: `e_${e.from}_${e.branch || 'x'}_${e.to}`,
    source: e.from, target: e.to,
    sourceHandle: e.branch || null, targetHandle: null,
    label: BRANCH_LABELS[e.branch] || e.branch || '',
    data: { branch: e.branch || null },
  }))
}

function loadDraft() {
  let def = null
  try { def = JSON.parse(sessionStorage.getItem('grt_wf_draft') || 'null') } catch { def = null }
  if (!def?.nodes?.length) return
  sessionStorage.removeItem('grt_wf_draft')
  applyDefinition(def, false)
  tidyUp()   // AI 草稿落点后自动整理一次画布
  if (def.notes) {
    ElMessageBox.alert(def.notes, 'AI 生成说明（请确认后保存）', { confirmButtonText: '知道了' })
  } else {
    ElMessage.success('AI 已生成工作流草稿，请确认后保存')
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onEditorKeydown)
  ;[tables.value, providers.value, nodeTypes.value, allWorkflows.value] = await Promise.all([
    listTables(), listProviders(), workflowNodeTypes(), listWorkflows(),
  ])
  if (wfId.value) {
    const wf = await getWorkflow(wfId.value)
    applyDefinition(wf)
    fitCanvas()
  } else if (route.query.draft) {
    loadDraft()
    fitCanvas()
  } else {
    // 新建：画布上先放好触发器节点并打开它的配置
    flowNodes.value = [makeTriggerNode({ x: 80, y: 120 })]
    selectedId.value = TRIGGER_ID
  }
  // 从运行详情「画布定位」跳入：选中并居中该节点（onNodesInitialized 后执行）
  if (route.query.node && flowNodes.value.some((n) => n.id === route.query.node)) {
    pendingFocus = String(route.query.node)
  }
  // 初始状态作为历史栈底（加载过程产生的中间快照丢弃）
  histStack.value = [snapshot()]
  histIndex.value = 0
})
onUnmounted(() => {
  window.removeEventListener('keydown', onEditorKeydown)
  clearTimeout(histTimer)
})
</script>

<style scoped>
/* 高度用 100%（填满 el-main 内容区），不能用 100vh：外层还有 48px 顶栏 + el-main 上下 padding，
   100vh 会超出可视区，导致页面右侧默认就出现滚动条 */
.wf-editor { height: 100%; display: flex; flex-direction: column; background: #f5f7fa; }
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
  cursor: grab; font-size: 12px; display: flex; align-items: center; gap: 6px;
}
.palette-item:hover { border-color: #409eff; background: #ecf5ff; }
/* 配置面板「最近运行」回显 */
.example-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.run-echo { margin-top: 8px; }
.run-echo-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.run-echo-err { font-size: 12px; color: #f56c6c; margin-bottom: 6px; }
.run-echo-warn { margin-bottom: 6px; }
.run-echo-io :deep(.el-collapse-item__header) { font-size: 12px; height: 34px; }
.run-echo-io :deep(.el-collapse-item__content) { max-height: 260px; overflow: auto; }
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
.config-panel { flex-shrink: 0; position: relative; background: #fff; border-left: 1px solid #e4e7ed; overflow-y: auto; padding: 12px; }
.panel-resizer { position: absolute; left: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; z-index: 5; }
.panel-resizer:hover { background: rgba(64, 158, 255, .35); }
.config-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.config-title { font-size: 13px; font-weight: 600; }
/* 问题清单抽屉 */
.issue-item {
  display: flex; gap: 8px; padding: 10px; border: 1px solid #e4e7ed; border-radius: 6px;
  margin-bottom: 8px; cursor: pointer; align-items: flex-start;
}
.issue-item:hover { border-color: #409eff; background: #ecf5ff; }
.issue-tag { flex-shrink: 0; margin-top: 1px; }
.issue-body { min-width: 0; }
.issue-node { font-size: 12px; font-weight: 600; color: #303133; }
.issue-msg { font-size: 12px; color: #606266; margin-top: 2px; line-height: 1.5; }
.run-err { font-size: 12px; color: #f56c6c; }
.explain-text { font-size: 14px; line-height: 1.8; color: #303133; white-space: pre-wrap; min-height: 60px; }
</style>
