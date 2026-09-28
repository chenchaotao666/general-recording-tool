<template>
  <div v-loading="loading" class="rp-designer">
    <!-- 顶栏（与工作流编辑器一致：白底通栏、名称内联编辑、操作按钮右排） -->
    <div class="topbar">
      <el-button link @click="goBack">
        <el-icon><ArrowLeft /></el-icon>返回
      </el-button>
      <el-input v-model="tplName" placeholder="报表名称" class="name-input" @input="dirty = true" />
      <el-tag v-if="dirty" size="small" type="warning" effect="plain">未保存</el-tag>

      <!-- 页签：顶栏居中（可横向滚动） -->
      <div class="page-bar">
        <div
          v-for="(p, pi) in pages" :key="p.id" class="page-tab" :class="{ active: p.id === activePageId }"
          @click="activePageId = p.id" @dblclick="renamePage(p)"
        >
          <span>{{ p.title }}</span>
          <template v-if="p.id === activePageId">
            <el-icon v-if="pi > 0" title="前移" @click.stop="movePage(pi, -1)"><ArrowLeftBold /></el-icon>
            <el-icon v-if="pi < pages.length - 1" title="后移" @click.stop="movePage(pi, 1)"><ArrowRightBold /></el-icon>
            <el-icon title="重命名" @click.stop="renamePage(p)"><EditPen /></el-icon>
            <el-icon v-if="pages.length > 1" title="删除页签" @click.stop="deletePage(p)"><Close /></el-icon>
          </template>
        </div>
        <el-button v-if="pages.length < PAGES_MAX" link type="primary" :icon="Plus" @click="addPage">页签</el-button>
      </div>

      <div class="spacer" />
      <el-button :disabled="!undoStack.length" title="撤销" @click="undo">撤销</el-button>
      <el-button :disabled="!redoStack.length" title="重做" @click="redo">重做</el-button>
      <el-button class="ai-btn" title="用一句话描述需求，AI 生成区块草稿" @click="openAi">
        <el-icon><MagicStick /></el-icon>AI 生成
      </el-button>
      <el-button @click="autoArrange">自动排版</el-button>
      <el-button :loading="previewLoading" title="沙盒试运行：用当前未保存的配置生成预览，不落库" @click="previewRun">试运行</el-button>
      <el-button @click="openSettings">设置</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </div>

    <div class="body">
      <!-- 左：数据源树（拖字段成图）+ 未放置区块 -->
      <div class="sidebar">
        <div class="side-section">
          <div class="side-title">
            数据源
            <el-button link type="primary" size="small" style="float: right" @click="addDatasetVisible = true">+ 添加</el-button>
          </div>
          <div v-for="d in datasets" :key="d.id" class="ds-group">
            <div class="ds-head">
              <span class="ds-name">{{ d.name }}</span>
              <el-icon title="编辑数据集（关联/计算字段）" @click="openDatasetEditor(d)"><Setting /></el-icon>
            </div>
            <div
              v-for="f in fieldsOf(d.id)" :key="f.field_name" class="field-chip" draggable="true"
              :title="`${f.label}（${f.data_type}）— 拖入画布成图`" @dragstart="onFieldDragStart($event, d, f)"
            >
              <span class="fc-type" :class="ftypeClass(f)">{{ ftypeShort(f) }}</span>
              <span class="fc-label">{{ f.label }}</span>
            </div>
          </div>
          <el-empty v-if="!datasets.length" description="先添加一个数据源" :image-size="40" />
        </div>
      </div>

      <!-- 栅格画布（点空白处收起配置面板） -->
      <div ref="canvasEl" class="canvas-wrap" @dragover.prevent @drop="onFieldDrop" @click="onCanvasBackdropClick">
        <GridLayout
          :layout="glItems" :col-num="GRID_COLS" :row-height="ROW_HEIGHT"
          :margin="[GRID_MARGIN, GRID_MARGIN]" :vertical-compact="false" @layout-updated="onLayoutUpdated"
        >
          <GridItem
            v-for="item in glItems" :key="item.i" v-bind="item"
            drag-allow-from=".gi-head" drag-ignore-from="button, a"
          >
            <div class="gi-card" :class="{ selected: item.i === selectedBlockId }" @click.stop="selectedBlockId = item.i">
              <div class="gi-head">
                <span class="gi-type">{{ BLOCK_TYPE_LABELS[blockOf(item.i)?.type] || '区块' }}</span>
                <span class="gi-title">{{ blockOf(item.i)?.title || '未命名' }}</span>
                <span v-if="dsOf(blockOf(item.i))" class="gi-ds">{{ dsOf(blockOf(item.i)).name }}</span>
                <el-button text size="small" :icon="Close" title="删除区块" @click.stop="removeBlock(item.i)" />
              </div>
              <!-- 真实数据渲染（draft 沙盒取数）；无数据时显示占位提示 -->
              <div v-if="blockResults[item.i]" class="gi-real">
                <ReportBlock :block="blockResults[item.i]" fill />
              </div>
              <div v-else class="gi-body">{{ dataLoading ? '绘制中…' : '点右侧「应用并绘制」加载数据' }}</div>
            </div>
          </GridItem>
        </GridLayout>
        <div v-if="!glItems.length" class="empty-hint">从左侧拖字段到画布自动成图，或点「自动排版」一键布局</div>
      </div>

      <!-- 右：选中区块的内联配置（浮动覆盖画布，不推挤布局；可拖宽） -->
      <div v-if="selectedBlock" class="config-panel" :style="{ width: panelWidth + 'px' }">
        <div class="panel-resizer" title="拖动调整宽度" @mousedown="startResize" />
        <div class="config-head">
          <span class="config-title">{{ BLOCK_TYPE_LABELS[selectedBlock.type] }}配置</span>
          <div>
            <el-button link type="danger" size="small" @click="removeBlock(selectedBlock.id)">删除区块</el-button>
            <el-button link type="info" size="small" @click="selectedBlockId = null">收起</el-button>
          </div>
        </div>
        <el-input v-model="selectedBlock.title" placeholder="区块显示名" size="small" class="mb" @input="dirty = true" />

        <el-form v-if="selectedBlock.type !== 'text'" label-position="top" size="small" @change="dirty = true">
          <el-form-item label="数据源">
            <el-select
              :model-value="selectedBlock.dataset_id" class="w-full"
              @change="(v) => onBlockDatasetChange(selectedBlock, v)"
            >
              <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期字段（全局口径作用字段）">
            <el-select v-model="selectedBlock.date_field" class="w-full" placeholder="日期字段">
              <el-option label="不随时间筛选" :value="null" />
              <el-option label="创建时间" value="created_at" />
              <el-option label="更新时间" value="updated_at" />
              <el-option v-for="f in dateFieldsOf(selectedBlock.dataset_id)" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-select v-model="rangeModeOf" class="w-full">
              <el-option label="跟随全局口径" value="" />
              <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="selectedBlock.range_mode === 'custom'">
            <el-date-picker
              v-model="rangeCustomOf" type="daterange" value-format="YYYY-MM-DD"
              class="w-full" start-placeholder="开始" end-placeholder="结束"
            />
          </el-form-item>
        </el-form>

        <!-- 筛选组件的作用域 -->
        <el-form v-if="selectedBlock.type === 'filter'" label-position="top" size="small" @change="dirty = true">
          <el-form-item label="作用范围">
            <el-select v-model="filterTargetMode" class="w-full">
              <el-option label="同数据源的全部区块" value="same_dataset" />
              <el-option label="指定区块" value="blocks" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="filterTargetMode === 'blocks'">
            <el-select v-model="filterTargetIds" multiple class="w-full" placeholder="选择目标区块">
              <el-option
                v-for="b2 in sameDatasetBlocks" :key="b2.id"
                :label="`${BLOCK_TYPE_LABELS[b2.type]} · ${b2.title || b2.id}`" :value="b2.id"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <el-divider content-position="left">图表配置</el-divider>
        <BlockConfigForm :block="selectedBlock" :fields="fieldsOf(selectedBlock.dataset_id)" :stat-blocks="statBlocks" />
        <el-button
          type="primary" size="small" class="w-full" style="margin-top: 14px"
          :loading="dataLoading" @click="refreshData()"
        >应用并绘制</el-button>
        <div class="panel-tip">改完点「应用并绘制」刷新画布数据；顶栏「保存」才会写入报表</div>
      </div>
    </div>

    <!-- 添加数据源 -->
    <el-dialog v-model="addDatasetVisible" title="添加数据源" width="420px" destroy-on-close>
      <el-select v-model="newDatasetTableId" placeholder="选择数据表" style="width: 100%" filterable>
        <el-option v-for="t in tables" :key="t.id" :label="`${t.label}（${t.storage_mode === 'physical' ? '物理' : 'JSON'}）`" :value="t.id" />
      </el-select>
      <template #footer>
        <el-button @click="addDatasetVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newDatasetTableId" @click="addDataset">添加</el-button>
      </template>
    </el-dialog>

    <!-- 数据集编辑：多表关联 + 计算字段 -->
    <el-drawer v-model="dsEditorVisible" :title="`数据集：${editingDs?.name || ''}`" size="560px">
      <template v-if="editingDs">
        <el-form label-width="80px">
          <el-form-item label="名称">
            <el-input v-model="editingDs.name" maxlength="32" style="width: 240px" />
          </el-form-item>
        </el-form>
        <div class="src-sec">
          <div class="src-title">
            关联表（左连接，最多 3 张，仅物理存储表）
            <el-button text type="primary" size="small" :disabled="editingDs.joins.length >= 3" @click="editingDs.joins.push({ table_id: null, prefix: '', on: [{ left: null, right: null }] })">+ 添加</el-button>
          </div>
          <div v-for="(j, ji) in editingDs.joins" :key="ji" class="join-card">
            <div class="join-row">
              <el-select
                v-model="j.table_id" size="small" placeholder="选择表" style="width: 170px" filterable
                @change="onJoinTableChange(j)"
              >
                <el-option v-for="t in joinableTables" :key="t.id" :label="t.label" :value="t.id" />
              </el-select>
              <el-input v-model="j.prefix" size="small" placeholder="字段前缀，如：客户." style="width: 150px" />
              <el-button text type="danger" size="small" @click="editingDs.joins.splice(ji, 1)">删除</el-button>
            </div>
            <div v-for="(o, oi) in j.on" :key="oi" class="join-row">
              <el-select v-model="o.left" size="small" placeholder="本表字段" style="width: 170px" filterable>
                <el-option v-for="f in baseFieldsOf(editingDs.base_table_id)" :key="f.field_name" :label="f.label" :value="f.field_name" />
                <el-option label="ID" value="id" />
              </el-select>
              <span style="color: #909399">=</span>
              <el-select v-model="o.right" size="small" placeholder="关联表字段" style="width: 170px" filterable>
                <el-option label="ID" value="id" />
                <el-option v-for="f in joinFieldsOf(j.table_id)" :key="f.field_name" :label="f.label" :value="f.field_name" />
              </el-select>
              <el-button text type="danger" size="small" :disabled="j.on.length <= 1" @click="j.on.splice(oi, 1)">删条件</el-button>
            </div>
            <el-button text size="small" @click="j.on.push({ left: null, right: null })">+ 关联条件</el-button>
          </div>
          <el-empty v-if="!editingDs.joins.length" description="暂无关联，单表可留空" :image-size="40" />
        </div>

        <div class="src-sec">
          <div class="src-title">
            计算字段（行内表达式）
            <el-button text type="primary" size="small" @click="editingDs.computed_fields.push({ name: '', expr: '', type: '' })">+ 添加</el-button>
          </div>
          <div v-for="(c, ci) in editingDs.computed_fields" :key="ci" class="cf-row">
            <el-input v-model="c.name" size="small" placeholder="字段名" style="width: 110px" />
            <el-input v-model="c.expr" size="small" placeholder="表达式，如：amount * 0.13" style="flex: 1" />
            <el-select v-model="c.type" size="small" placeholder="自动" clearable style="width: 90px">
              <el-option label="整数" value="int" />
              <el-option label="小数" value="decimal" />
              <el-option label="布尔" value="bool" />
              <el-option label="文本" value="varchar" />
            </el-select>
            <el-button text type="danger" size="small" @click="editingDs.computed_fields.splice(ci, 1)">删</el-button>
          </div>
          <div class="src-tip">
            支持 + - * /、比较、and/or、iff(条件,a,b)、coalesce、abs、round、floor、ceil、min、max、year、month、day、datediff；
            引用关联字段用「前缀.字段名」，如：iff(客户.level == 'A', 1, 0)
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="dsEditorVisible = false">关闭</el-button>
        <el-button type="primary" @click="applyDatasetEditor">应用</el-button>
      </template>
    </el-drawer>

    <!-- 模板设置：口径/推送（名称在顶栏编辑，AI 生成在顶栏） -->
    <el-drawer v-model="settingsVisible" title="报表设置" size="520px">
      <el-form label-width="90px">
        <el-form-item label="描述">
          <el-input v-model="settingsForm.description" placeholder="选填" />
        </el-form-item>
        <el-form-item label="全局口径">
          <el-select v-model="settingsForm.range.mode" style="width: 140px">
            <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
          </el-select>
          <el-date-picker
            v-if="settingsForm.range.mode === 'custom'" v-model="settingsRangeCustom" type="daterange"
            value-format="YYYY-MM-DD" style="margin-left: 8px; width: 240px"
            start-placeholder="开始" end-placeholder="结束"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            各区块按自己的日期字段套用该时间范围；块可单独覆盖或设为"不随时间筛选"
          </div>
        </el-form-item>

        <el-divider content-position="left">定时推送（可选）</el-divider>
        <el-form-item label="执行周期">
          <el-radio-group v-model="settingsForm.schedule.type">
            <el-radio value="">不定时</el-radio>
            <el-radio value="interval">每隔</el-radio>
            <el-radio value="cron">cron</el-radio>
          </el-radio-group>
          <template v-if="settingsForm.schedule.type === 'interval'">
            <el-input-number v-model="settingsForm.schedule.minutes" :min="1" controls-position="right" style="margin: 0 8px; width: 110px" />
            分钟
          </template>
          <template v-else-if="settingsForm.schedule.type === 'cron'">
            <el-input v-model="settingsForm.schedule.expr" style="width: 150px; margin-left: 8px" placeholder="分 时 日 月 周" />
          </template>
        </el-form-item>
        <template v-if="settingsForm.schedule.type">
          <el-form-item label="收件邮箱">
            <el-input v-model="settingsForm.push.recipients" placeholder="多个用逗号分隔" />
          </el-form-item>
          <el-form-item label="群机器人">
            <div style="width: 100%">
              <div v-for="(wh, i) in settingsForm.push.webhooks" :key="i" style="display: flex; gap: 8px; margin-bottom: 8px">
                <el-select v-model="wh.type" style="width: 100px">
                  <el-option label="企业微信" value="wecom" />
                  <el-option label="钉钉" value="dingtalk" />
                  <el-option label="自定义" value="custom" />
                </el-select>
                <el-input v-model="wh.url" placeholder="Webhook 地址" style="flex: 1" />
                <el-button text type="danger" @click="settingsForm.push.webhooks.splice(i, 1)">删</el-button>
              </div>
              <el-button text type="primary" size="small" @click="settingsForm.push.webhooks.push({ type: 'wecom', url: '' })">+ 添加机器人</el-button>
            </div>
          </el-form-item>
          <el-form-item label="推送内容">
            <el-checkbox-group v-model="settingsForm.push.formats">
              <el-checkbox value="html_inline">邮件正文</el-checkbox>
              <el-checkbox value="xlsx">Excel 附件</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="邮件主题">
            <el-input v-model="settingsForm.push.subject" placeholder="默认：【报表名】时间范围" />
          </el-form-item>
          <el-form-item label="启用推送">
            <el-switch v-model="settingsForm.enabled" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="applySettings">应用</el-button>
      </template>
    </el-drawer>

    <!-- AI 辅助 -->
    <el-dialog v-model="aiVisible" title="AI 辅助生成报表" width="640px" destroy-on-close>
      <el-select v-model="aiTableId" placeholder="基于哪张表生成" style="width: 100%; margin-bottom: 10px" filterable>
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <el-input
        v-model="aiDescription" type="textarea" :rows="4"
        placeholder="用自然语言描述你想要的报表，如：做一个上周的客户跟进周报，包含新增客户数、客户分级占比、每日新增趋势、客户明细和一段小结"
      />
      <div style="margin: 10px 0">
        <el-button type="primary" :loading="aiGenerating" :disabled="!aiTableId || !aiDescription.trim()" @click="aiGenerate">
          {{ aiResult ? '重新生成' : '生成' }}
        </el-button>
        <span v-if="aiGenerating" style="margin-left: 10px; font-size: 12px; color: #909399">AI 设计中，可能需要十几秒…</span>
      </div>
      <template v-if="aiResult">
        <el-alert type="success" :closable="false" style="margin-bottom: 10px"
          :title="`已生成「${aiResult.name}」：${aiResult.blocks.length} 个区块`" />
        <el-alert v-if="aiResult.notes" type="warning" :closable="false" :title="aiResult.notes" style="margin-bottom: 10px" />
      </template>
      <template #footer>
        <el-button @click="aiVisible = false">取消</el-button>
        <el-button v-if="aiResult" type="primary" @click="aiApply">应用（替换全部区块）</el-button>
      </template>
    </el-dialog>

    <!-- 试运行预览（draft 不落库） -->
    <el-dialog v-model="previewVisible" title="试运行预览（未保存的配置，不影响线上报表）" width="88%" top="4vh">
      <div v-loading="previewLoading" style="min-height: 200px">
        <ReportDashboard v-if="previewResult" :blocks="previewResult.blocks" :layout="previewResult.layout" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, ArrowLeftBold, ArrowRightBold, Close, EditPen, MagicStick, Plus, Setting,
} from '@element-plus/icons-vue'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { aiAssistReport, getReport, getTable, listTables, runReport, updateReport } from '../api'
import ReportDashboard from '../components/ReportDashboard.vue'
import ReportBlock from '../components/ReportBlock.vue'
import BlockConfigForm from '../components/BlockConfigForm.vue'
import {
  BLOCK_SIZE, BLOCK_TYPE_LABELS, GRID_COLS, GRID_MARGIN, PAGES_MAX, ROW_HEIGHT,
  autoLayout, defaultItem, nextPageId, normalizeLayout, smartBlockForField,
} from '../utils/reportLayout'

const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]

const route = useRoute()
const router = useRouter()
const tplId = route.params.id

const loading = ref(false)
const saving = ref(false)
const tpl = ref(null)
const pages = ref([])
const activePageId = ref('')
const dirty = ref(false)

const blocks = computed(() => tpl.value?.blocks || [])
const statBlocks = computed(() => blocks.value.filter((b) => b.type === 'stat'))
const activePage = computed(() => pages.value.find((p) => p.id === activePageId.value))

// 顶栏名称内联编辑（与工作流编辑器一致）
const tplName = computed({
  get: () => tpl.value?.name || '',
  set: (v) => { if (tpl.value) tpl.value.name = v },
})

// 右侧配置面板：可拖宽（与工作流编辑器一致）
const panelWidth = ref(400)

function startResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startW = panelWidth.value
  const onMove = (ev) => {
    panelWidth.value = Math.min(640, Math.max(320, startW + (startX - ev.clientX)))
  }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function blockOf(id) {
  return blocks.value.find((b) => b.id === id)
}

// ---------- 数据集 ----------
const datasets = ref([])
const fieldMap = ref({})       // dataset_id -> 数据集字段（含关联/计算）
const baseFieldMap = ref({})   // table_id -> 基表字段
const tables = ref([])
const joinMeta = ref({})       // table_id -> fields（关联表）

let dsSeq = 0
function nextDatasetId() {
  const existing = new Set(datasets.value.map((d) => d.id))
  do { dsSeq += 1 } while (existing.has(`d${dsSeq}`))
  return `d${dsSeq}`
}

function dsOf(block) {
  if (!block || block.type === 'text') return null
  return datasets.value.find((d) => d.id === block.dataset_id) || null
}

function fieldsOf(did) {
  return fieldMap.value[did] || []
}

function baseFieldsOf(tid) {
  return baseFieldMap.value[tid] || []
}

function dateFieldsOf(did) {
  return fieldsOf(did).filter((f) => ['date', 'datetime'].includes(f.data_type))
}

function joinFieldsOf(tid) {
  return joinMeta.value[tid] || []
}

async function loadBaseFields(tid) {
  if (!baseFieldMap.value[tid]) {
    const t = await getTable(tid)
    baseFieldMap.value[tid] = t.fields
  }
  return baseFieldMap.value[tid]
}

async function refreshFields(did) {
  const d = datasets.value.find((x) => x.id === did)
  if (!d) return
  const base = await loadBaseFields(d.base_table_id)
  let out = [...base]
  for (const j of d.joins || []) {
    if (!j.table_id || !j.prefix) continue
    if (!joinMeta.value[j.table_id]) {
      joinMeta.value[j.table_id] = (await getTable(j.table_id)).fields
    }
    out = out.concat(joinMeta.value[j.table_id].map((f) => ({
      ...f, field_name: j.prefix + f.field_name, label: j.prefix + f.label,
    })))
  }
  for (const c of d.computed_fields || []) {
    if (c.name?.trim()) out.push({ field_name: c.name.trim(), label: c.name.trim(), data_type: c.type || 'decimal' })
  }
  fieldMap.value = { ...fieldMap.value, [did]: out }
}

async function refreshAllFields() {
  for (const d of datasets.value) await refreshFields(d.id)
}

// 添加数据源
const addDatasetVisible = ref(false)
const newDatasetTableId = ref(null)

async function addDataset() {
  const t = tables.value.find((x) => x.id === newDatasetTableId.value)
  const d = { id: nextDatasetId(), name: t?.label || '', base_table_id: newDatasetTableId.value, joins: [], computed_fields: [] }
  datasets.value.push(d)
  addDatasetVisible.value = false
  newDatasetTableId.value = null
  await refreshFields(d.id)
  dirty.value = true
  ElMessage.success(`已添加数据源「${d.name}」，拖字段到画布即可成图`)
}

// 数据集编辑抽屉
const dsEditorVisible = ref(false)
const editingDs = ref(null)

const joinableTables = computed(() =>
  tables.value.filter((t) => t.storage_mode === 'physical' && t.id !== editingDs.value?.base_table_id)
)

async function openDatasetEditor(d) {
  editingDs.value = d
  await loadBaseFields(d.base_table_id)
  for (const j of d.joins || []) {
    if (j.table_id && !joinMeta.value[j.table_id]) {
      joinMeta.value[j.table_id] = (await getTable(j.table_id)).fields
    }
  }
  dsEditorVisible.value = true
}

async function onJoinTableChange(j) {
  j.on = [{ left: null, right: null }]
  if (j.table_id && !joinMeta.value[j.table_id]) {
    joinMeta.value[j.table_id] = (await getTable(j.table_id)).fields
  }
  if (!j.prefix && j.table_id) {
    const t = tables.value.find((x) => x.id === j.table_id)
    j.prefix = t ? `${t.label}.` : ''
  }
}

async function applyDatasetEditor() {
  dsEditorVisible.value = false
  if (editingDs.value) await refreshFields(editingDs.value.id)
  dirty.value = true
  ElMessage.success('数据集已应用，保存后生效')
  refreshData(true)   // 数据集变更后重绘
}

// ---------- 选中区块的内联编辑 ----------
const selectedBlockId = ref(null)
const selectedBlock = computed(() => blockOf(selectedBlockId.value))

const rangeModeOf = computed({
  get: () => selectedBlock.value?.range_mode || '',
  set: (v) => {
    const b = selectedBlock.value
    if (!b) return
    if (v) {
      b.range_mode = v
    } else {
      delete b.range_mode
      delete b.range_start
      delete b.range_end
    }
  },
})

const rangeCustomOf = computed({
  get: () => (selectedBlock.value?.range_start && selectedBlock.value?.range_end
    ? [selectedBlock.value.range_start, selectedBlock.value.range_end] : null),
  set: (v) => {
    const b = selectedBlock.value
    if (!b) return
    b.range_start = v?.[0] || null
    b.range_end = v?.[1] || null
  },
})

// 筛选组件作用域
const filterTargetMode = computed({
  get: () => selectedBlock.value?.target?.mode || 'same_dataset',
  set: (v) => {
    const b = selectedBlock.value
    if (!b) return
    b.target = v === 'blocks' ? { mode: 'blocks', block_ids: b.target?.block_ids || [] } : { mode: 'same_dataset' }
  },
})
const filterTargetIds = computed({
  get: () => selectedBlock.value?.target?.block_ids || [],
  set: (v) => { if (selectedBlock.value) selectedBlock.value.target = { mode: 'blocks', block_ids: v } },
})
const sameDatasetBlocks = computed(() =>
  blocks.value.filter((b) => b.dataset_id === selectedBlock.value?.dataset_id && b.id !== selectedBlock.value?.id && !['text', 'filter'].includes(b.type))
)

let blockSeq = 0
function nextBlockId() {
  const existing = new Set(blocks.value.map((b) => b.id))
  do { blockSeq += 1 } while (existing.has(`b${blockSeq}`))
  return `b${blockSeq}`
}

// 区块换源：同名字段保留，冲突配置清空
function onBlockDatasetChange(block, did) {
  block.dataset_id = did
  const valid = new Set(fieldsOf(did).map((f) => f.field_name))
  const keep = (fn) => (fn && (valid.has(fn) || ['created_at', 'updated_at', 'id'].includes(fn)) ? fn : null)
  const dropped = []
  for (const key of ['field']) {
    if (block[key] && !keep(block[key])) { block[key] = null; dropped.push(key) }
  }
  if (block.group && block.group.field && !keep(block.group.field)) { block.group.field = null; dropped.push('group') }
  if (block.group2?.field && !keep(block.group2.field)) { block.group2.field = null; dropped.push('group2') }
  if (block.row?.field && !keep(block.row.field)) block.row.field = null
  if (block.col?.field && !keep(block.col.field)) block.col.field = null
  if (Array.isArray(block.columns)) block.columns = block.columns.filter(keep)
  if (block.filters?.rules) block.filters.rules = block.filters.rules.filter((r) => keep(r.field))
  if (block.type === 'filter' && !keep(block.field)) block.field = null
  if (block.date_field && !['created_at', 'updated_at'].includes(block.date_field) && !valid.has(block.date_field)) {
    block.date_field = 'created_at'
  }
  dirty.value = true
  if (dropped.length) ElMessage.warning(`换源后部分配置因字段不存在已清空：${dropped.join('、')}`)
}

// 真删除区块（画布 ✕ 与面板按钮共用）：从模板与所有页签移除
async function removeBlock(blockId) {
  const b = blockOf(blockId)
  if (!b) return
  try {
    await ElMessageBox.confirm(`确定删除区块「${b.title || b.id}」？删除后不可恢复（可撤销保存前的修改）。`, '删除区块', { type: 'warning' })
  } catch { return }
  tpl.value.blocks = blocks.value.filter((x) => x.id !== b.id)
  for (const p of pages.value) p.items = p.items.filter((it) => it.block_id !== b.id)
  if (selectedBlockId.value === b.id) selectedBlockId.value = null
  dirty.value = true
  commit()
  layoutVersion.value++
}

// ---------- 拖字段成图 ----------
let dragPayload = null
const canvasEl = ref(null)

function onFieldDragStart(e, d, f) {
  dragPayload = { did: d.id, field: f }
  e.dataTransfer.effectAllowed = 'copy'
}

// 鼠标落点 → 栅格坐标（块中心对准光标，越界收敛；取不到容器时返回 null 回退底部追加）
function dropPosition(e, w, h) {
  const gl = canvasEl.value?.querySelector('.vgl-layout')
  if (!gl) return null
  const rect = gl.getBoundingClientRect()
  const colW = (rect.width - (GRID_COLS - 1) * GRID_MARGIN) / GRID_COLS
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  if (px < 0 || py < 0) return null
  const gx = Math.min(Math.max(Math.round(px / (colW + GRID_MARGIN) - w / 2), 0), GRID_COLS - w)
  let gy = Math.max(Math.round(py / (ROW_HEIGHT + GRID_MARGIN)) - 1, 0)
  // 避免与现有块重叠：有重叠时下移到其底边（保持鼠标所在列）
  const items = activePage.value?.items || []
  const overlapped = (y) => items.some((it) => gx < it.x + it.w && gx + w > it.x && y < it.y + it.h && y + h > it.y)
  let guard = 0
  while (overlapped(gy) && guard++ < 200) gy += 1
  return { x: gx, y: gy, w, h }
}

function ftypeShort(f) {
  return { int: '数', decimal: '数', date: '期', datetime: '期', bool: '否' }[f.data_type] || '文'
}

function ftypeClass(f) {
  if (['int', 'decimal'].includes(f.data_type)) return 'num'
  if (['date', 'datetime'].includes(f.data_type)) return 'date'
  if (f.data_type === 'bool') return 'bool'
  return 'text'
}

function onFieldDrop(e) {
  e.preventDefault()
  if (!dragPayload || !activePage.value) return
  const b = {
    id: nextBlockId(), ...smartBlockForField(dragPayload.field),
    dataset_id: dragPayload.did,
    date_field: ['date', 'datetime'].includes(dragPayload.field.data_type) ? dragPayload.field.field_name : 'created_at',
  }
  tpl.value.blocks.push(b)
  const { def } = BLOCK_SIZE[b.type] || BLOCK_SIZE.text
  const pos = dropPosition(e, ...def) || defaultItem(b, activePage.value.items)
  activePage.value.items.push({ block_id: b.id, x: pos.x, y: pos.y, w: pos.w, h: pos.h })
  selectedBlockId.value = b.id
  dirty.value = true
  commit()
  layoutVersion.value++
  ElMessage.success(`已生成「${b.title}」`)
  dragPayload = null
  refreshData(true)   // 新块立即绘制
}

// 点画布空白处收起配置面板（点块时 gi-card 已 stop）
function onCanvasBackdropClick(e) {
  if (!e.target.closest('.gi-card')) selectedBlockId.value = null
}

function onKeydown(e) {
  if (e.key === 'Escape' && selectedBlockId.value) selectedBlockId.value = null
}

// ---------- 画布实时绘制（draft 沙盒取数，不落库） ----------
const blockResults = ref({})   // block_id -> run 结果块
const dataLoading = ref(false)

function buildDraft() {
  return {
    datasets: cleanedDatasets(),
    blocks: cleanedBlocks(blocks.value),
    layout: layoutData(),
    range: { mode: tpl.value.range?.mode || 'this_week', start: tpl.value.range?.start, end: tpl.value.range?.end },
  }
}

async function refreshData(silent = false) {
  if (!blocks.value.length) {
    blockResults.value = {}
    return
  }
  dataLoading.value = true
  try {
    const res = await runReport(tplId, null, null, null, buildDraft())
    blockResults.value = Object.fromEntries((res.blocks || []).map((b) => [b.id, b]))
  } catch (e) {
    if (!silent) ElMessage.error(`绘制失败：${e.message}`)
  } finally {
    dataLoading.value = false
  }
}

// GridLayout 内部态与 pages 解耦（关键：库在拖动时不发 update:layout，只在 dragend/resizeend 发 layout-updated）：
// ① 结构变化（换页/撤销/放置/排版/删除）→ layoutVersion++ → syncGlItems 重建布局数组；
// ② 拖动/缩放结束 → onLayoutUpdated 把坐标写回 pages。
const glItems = ref([])
const layoutVersion = ref(0)

function syncGlItems() {
  glItems.value = (activePage.value?.items || []).map((it) => {
    const { min } = BLOCK_SIZE[blockOf(it.block_id)?.type] || BLOCK_SIZE.text
    return { i: it.block_id, x: it.x, y: it.y, w: it.w, h: it.h, minW: min[0], minH: min[1] }
  })
}

watch([activePageId, layoutVersion], syncGlItems, { immediate: true })

function onLayoutUpdated(arr) {
  if (!activePage.value) return
  const byI = new Map(arr.map((it) => [it.i, it]))
  activePage.value.items = activePage.value.items.map((it) => {
    const g = byI.get(it.block_id)
    return g ? { block_id: it.block_id, x: g.x, y: g.y, w: g.w, h: g.h } : it
  })
  commit()
}

// ---------- 撤销 / 重做 ----------
const undoStack = ref([])
const redoStack = ref([])
let lastCommitted = ''

const snapshot = () => JSON.stringify(pages.value)

function commit() {
  const cur = snapshot()
  if (cur === lastCommitted) return
  undoStack.value.push(lastCommitted)
  if (undoStack.value.length > 50) undoStack.value.shift()
  lastCommitted = cur
  redoStack.value = []
  dirty.value = true
}

function restore(json) {
  pages.value = JSON.parse(json)
  if (!pages.value.some((p) => p.id === activePageId.value)) activePageId.value = pages.value[0]?.id || ''
  dirty.value = true
  layoutVersion.value++
}

function undo() {
  if (!undoStack.value.length) return
  redoStack.value.push(lastCommitted)
  lastCommitted = undoStack.value.pop()
  restore(lastCommitted)
}

function redo() {
  if (!redoStack.value.length) return
  undoStack.value.push(lastCommitted)
  lastCommitted = redoStack.value.pop()
  restore(lastCommitted)
}

// ---------- 区块放置 ----------
function place(block) {
  if (!activePage.value) return
  activePage.value.items.push(defaultItem(block, activePage.value.items))
  commit()
  layoutVersion.value++
}

function autoArrange() {
  const p = activePage.value
  if (!p) return
  const pageBlocks = p.items.map((it) => blockOf(it.block_id)).filter(Boolean)
  p.items = autoLayout(pageBlocks).pages[0].items
  commit()
  layoutVersion.value++
  ElMessage.success('已按规则自动排版')
}

// ---------- 页签管理 ----------
function addPage() {
  const id = nextPageId(pages.value)
  pages.value.push({ id, title: `页签${pages.value.length + 1}`, items: [] })
  activePageId.value = id
  commit()
}

async function renamePage(p) {
  try {
    const { value } = await ElMessageBox.prompt('页签名称（≤20 字）', '重命名', {
      inputValue: p.title, inputValidator: (v) => (v?.trim().length ? (v.trim().length <= 20 || '不能超过 20 字') : '不能为空'),
    })
    p.title = value.trim()
    commit()
  } catch { /* 取消 */ }
}

async function deletePage(p) {
  try {
    await ElMessageBox.confirm(
      p.items.length ? `删除页签「${p.title}」？页内 ${p.items.length} 个区块将一并删除。` : `删除页签「${p.title}」？`,
      '删除页签', { type: 'warning' },
    )
  } catch { return }
  // 页内区块一并删除（已无"未放置"暂存区）
  const ids = new Set(p.items.map((it) => it.block_id))
  if (ids.size) {
    tpl.value.blocks = blocks.value.filter((b) => !ids.has(b.id))
    for (const other of pages.value) other.items = other.items.filter((it) => !ids.has(it.block_id))
    if (selectedBlockId.value && ids.has(selectedBlockId.value)) selectedBlockId.value = null
  }
  pages.value = pages.value.filter((x) => x.id !== p.id)
  if (activePageId.value === p.id) activePageId.value = pages.value[0]?.id || ''
  commit()
}

function movePage(pi, dir) {
  const arr = pages.value
  ;[arr[pi], arr[pi + dir]] = [arr[pi + dir], arr[pi]]
  commit()
}

// ---------- 模板设置 ----------
const settingsVisible = ref(false)
const settingsForm = reactive({
  name: '', description: '', enabled: false,
  range: { mode: 'this_week', start: null, end: null },
  schedule: { type: '', minutes: 60, expr: '0 9 * * 1' },
  push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [] },
})

const settingsRangeCustom = computed({
  get: () => (settingsForm.range.start && settingsForm.range.end ? [settingsForm.range.start, settingsForm.range.end] : null),
  set: (v) => {
    settingsForm.range.start = v?.[0] || null
    settingsForm.range.end = v?.[1] || null
  },
})

function openSettings() {
  const t = tpl.value
  Object.assign(settingsForm, {
    description: t.description || '', enabled: t.enabled,
    range: { mode: t.range?.mode || 'this_week', start: t.range?.start || null, end: t.range?.end || null },
    schedule: { type: '', minutes: 60, expr: '0 9 * * 1', ...(t.schedule || {}) },
    push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [], ...(t.push || {}) },
  })
  settingsVisible.value = true
}

function applySettings() {
  tpl.value.description = settingsForm.description
  tpl.value.enabled = settingsForm.schedule.type ? settingsForm.enabled : false
  tpl.value.range = { mode: settingsForm.range.mode, start: settingsForm.range.start, end: settingsForm.range.end }
  tpl.value.schedule = settingsForm.schedule.type
    ? (settingsForm.schedule.type === 'interval'
      ? { type: 'interval', minutes: settingsForm.schedule.minutes }
      : { type: 'cron', expr: settingsForm.schedule.expr })
    : {}
  tpl.value.push = settingsForm.schedule.type
    ? { ...settingsForm.push, webhooks: (settingsForm.push.webhooks || []).filter((w) => (w.url || '').trim()) }
    : {}
  settingsVisible.value = false
  dirty.value = true
  ElMessage.success('设置已应用，保存后生效')
}

// ---------- AI 辅助 ----------
const aiVisible = ref(false)
const aiTableId = ref(null)
const aiDescription = ref('')
const aiGenerating = ref(false)
const aiResult = ref(null)

function openAi() {
  aiResult.value = null
  aiTableId.value = datasets.value[0]?.base_table_id || null
  aiVisible.value = true
}

async function aiGenerate() {
  aiGenerating.value = true
  try {
    aiResult.value = await aiAssistReport(aiTableId.value, aiDescription.value.trim())
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiGenerating.value = false
  }
}

async function aiApply() {
  if (blocks.value.length) {
    try {
      await ElMessageBox.confirm('应用将替换当前全部区块并重排布局，确定继续？', 'AI 辅助', { type: 'warning' })
    } catch { return }
  }
  // 找到或创建该表对应的数据集
  let dset = datasets.value.find((d) => d.base_table_id === aiTableId.value)
  if (!dset) {
    const t = tables.value.find((x) => x.id === aiTableId.value)
    dset = { id: nextDatasetId(), name: t?.label || '', base_table_id: aiTableId.value, joins: [], computed_fields: [] }
    datasets.value.push(dset)
    await refreshFields(dset.id)
  }
  const df = aiResult.value.range?.date_field || 'created_at'
  tpl.value.blocks = aiResult.value.blocks.map((b) => ({
    ...b,
    filters: b.filters || { logic: 'AND', rules: [] },
    group: b.group ? { ...b.group } : undefined,
    dataset_id: dset.id,
    date_field: df,
    ...(b.type === 'pivot' ? {
      row: { kind: 'field', field: null, ...(b.row || {}) },
      col: { kind: 'field', field: null, ...(b.col || {}) },
      totals: b.totals !== false,
    } : {}),
  }))
  pages.value = autoLayout(tpl.value.blocks).pages
  activePageId.value = pages.value[0]?.id || ''
  tpl.value.range = { mode: aiResult.value.range?.mode || 'this_week', start: null, end: null }
  if (!tpl.value.name.trim()) tpl.value.name = aiResult.value.name
  aiVisible.value = false
  settingsVisible.value = false
  dirty.value = true
  lastCommitted = snapshot()
  layoutVersion.value++
  ElMessage.success('已应用，可继续调整后保存')
  refreshData(true)   // AI 生成后立即绘制
}

// ---------- 加载 / 保存 ----------
async function load() {
  loading.value = true
  try {
    tpl.value = await getReport(tplId)
    upgradeLegacy()
    const layoutData = tpl.value.layout
      ? normalizeLayout(tpl.value.layout, tpl.value.blocks || [])
      : autoLayout(tpl.value.blocks || [])
    pages.value = layoutData.pages
    activePageId.value = pages.value[0]?.id || ''
    undoStack.value = []
    redoStack.value = []
    lastCommitted = snapshot()
    dirty.value = !tpl.value.datasets?.length  // 旧模板升级后未落库，提示保存
    await refreshAllFields()
    refreshData(true)   // 打开即绘制真实数据
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// 旧格式（table_id + source + filter_fields）→ v3 结构（内存合成，保存即升级）
function upgradeLegacy() {
  const t = tpl.value
  if (t.datasets?.length) {
    datasets.value = t.datasets.map((d) => ({
      ...d, joins: d.joins || [], computed_fields: d.computed_fields || [],
    }))
    return
  }
  const d = {
    id: 'd1', name: t.table_label || '主数据集', base_table_id: t.table_id,
    joins: (t.source?.joins || []).map((j) => ({ ...j, on: (j.on || []).map((o) => ({ ...o })) })),
    computed_fields: (t.source?.computed_fields || []).map((c) => ({ type: '', ...c })),
  }
  datasets.value = [d]
  const df = t.range?.date_field || 'created_at'
  const newBlocks = []
  for (const b of t.blocks || []) {
    if (b.type === 'text') {
      newBlocks.push(b)
      continue
    }
    const nb = { ...b, dataset_id: b.dataset_id || 'd1' }
    if (!('date_field' in nb)) nb.date_field = df
    newBlocks.push(nb)
  }
  // 旧查看端筛选字段 → 筛选组件块（放到首页顶部）
  const fbs = (t.filter_fields || []).map((fn) => ({
    id: nextBlockId(), type: 'filter', title: fn, field: fn, dataset_id: 'd1',
    date_field: null, target: { mode: 'same_dataset' }, filters: { logic: 'AND', rules: [] },
  }))
  t.blocks = [...fbs, ...newBlocks]
  if (fbs.length && t.layout?.pages?.length) {
    // 有布局：插入到首页顶部（现有内容下移 2 行 × 每行 4 个）
    const page = t.layout.pages[0]
    const rows = Math.ceil(fbs.length / 4) * 2
    page.items = page.items.map((it) => ({ ...it, y: it.y + rows }))
    fbs.forEach((fb, i) => page.items.unshift({ block_id: fb.id, x: (i % 4) * 6, y: Math.floor(i / 4) * 2, w: 6, h: 2 }))
  }
}

function cleanedDatasets() {
  return datasets.value.map((d) => ({
    id: d.id,
    name: (d.name || '').trim() || d.id,
    base_table_id: d.base_table_id,
    joins: (d.joins || [])
      .filter((j) => j.table_id && j.prefix?.trim() && j.on.some((o) => o.left && o.right))
      .map((j) => ({ table_id: j.table_id, prefix: j.prefix.trim(), on: j.on.filter((o) => o.left && o.right) })),
    computed_fields: (d.computed_fields || [])
      .filter((c) => c.name?.trim() && c.expr?.trim())
      .map((c) => ({ name: c.name.trim(), expr: c.expr.trim(), ...(c.type ? { type: c.type } : {}) })),
  }))
}

function layoutData() {
  return {
    version: 1,
    grid: { cols: GRID_COLS, row_height: ROW_HEIGHT },
    pages: pages.value.map((p) => ({
      id: p.id,
      title: p.title,
      items: p.items.map((it) => ({ block_id: it.block_id, x: it.x, y: it.y, w: it.w, h: it.h })),
    })),
  }
}

function cleanedBlocks(list) {
  return list.map((b) => {
    const { series_mode, ...rest } = b
    return { ...rest, filters: { logic: b.filters.logic, rules: (b.filters.rules || []).filter((r) => r.field && r.op) } }
  })
}

function buildPayload() {
  const t = tpl.value
  const dsets = cleanedDatasets()
  return {
    name: (t.name || '').trim() || '未命名报表',
    description: t.description || null,
    table_id: dsets[0]?.base_table_id || t.table_id,
    enabled: t.enabled,
    range: { mode: t.range?.mode || 'this_week', start: t.range?.start || null, end: t.range?.end || null },
    blocks: cleanedBlocks(t.blocks || []),
    layout: layoutData(),
    source: null,
    datasets: dsets,
    filter_fields: [],
    schedule: t.schedule || {},
    push: t.push || {},
  }
}

async function save() {
  saving.value = true
  try {
    tpl.value = await updateReport(tplId, buildPayload())
    dirty.value = false
    lastCommitted = snapshot()
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

// ---------- 试运行（draft 沙盒，不落库） ----------
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewResult = ref(null)

async function previewRun() {
  previewVisible.value = true
  previewLoading.value = true
  previewResult.value = null
  try {
    previewResult.value = await runReport(tplId, null, null, null, buildDraft())
  } catch (e) {
    previewVisible.value = false
    ElMessage.error(e.message)
  } finally {
    previewLoading.value = false
  }
}

function goBack() {
  // 设计器是列表页「设计」入口进入的，返回即回列表
  if (dirty.value) {
    ElMessageBox.confirm('有未保存的修改，确定离开？', '提示', { type: 'warning' })
      .then(() => router.push('/reports'))
      .catch(() => {})
  } else {
    router.push('/reports')
  }
}

function onBeforeUnload(e) {
  if (dirty.value) e.preventDefault()
}

onMounted(async () => {
  await load()
  if (!tables.value.length) {
    try { tables.value = await listTables() } catch { /* 添加数据源时会重试 */ }
  }
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* 结构与工作流编辑器一致：白顶栏 + 左白栏 + 灰画布 + 右白配置面板（可拖宽）。
   高度用 100%（填满 el-main 内容区），不能用 100vh：外层还有顶栏 + el-main padding。 */
.rp-designer { height: 100%; display: flex; flex-direction: column; background: #f5f7fa; }
.topbar {
  display: flex; align-items: center; gap: 12px; padding: 8px 16px;
  background: #fff; border-bottom: 1px solid #e4e7ed;
}
.name-input { width: 220px; }
.spacer { flex: 1; }
.ai-btn { background: #9b59b6; border-color: #9b59b6; color: #fff; }
.ai-btn:hover, .ai-btn:focus { background: #8e44ad; border-color: #8e44ad; color: #fff; }

/* 页签：顶栏居中、可横向滚动 */
.page-bar {
  display: flex; align-items: center; gap: 6px; max-width: 44vw; overflow-x: auto;
  scrollbar-width: none;
}
.page-bar::-webkit-scrollbar { display: none; }
.page-tab {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; cursor: pointer;
  background: #f5f7fa; border: 1px solid #dcdfe6; border-radius: 6px; font-size: 13px; color: #606266;
  user-select: none; white-space: nowrap;
}
.page-tab.active { border-color: #409eff; color: #409eff; background: #ecf5ff; }
.page-tab .el-icon { font-size: 12px; color: #909399; }
.page-tab .el-icon:hover { color: #409eff; }

.body { flex: 1; display: flex; min-height: 0; position: relative; }

/* 左侧栏（与工作流节点面板一致：白底、右边线） */
.sidebar { width: 210px; background: #fff; border-right: 1px solid #e4e7ed; overflow-y: auto; padding: 10px; }
.side-section { margin-bottom: 18px; }
.side-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.ds-group { margin-bottom: 12px; }
.ds-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 2px; margin-bottom: 4px; }
.ds-name { font-size: 12px; font-weight: 600; color: #909399; }
.ds-head .el-icon { color: #909399; cursor: pointer; }
.ds-head .el-icon:hover { color: #409eff; }
.field-chip {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin-bottom: 4px; cursor: grab;
  border: 1px solid #e4e7ed; border-radius: 6px; font-size: 12px; background: #fff;
}
.field-chip:hover { border-color: #409eff; background: #ecf5ff; }
.fc-type { flex-shrink: 0; width: 18px; height: 18px; border-radius: 4px; font-size: 11px; text-align: center; line-height: 18px; color: #fff; }
.fc-type.num { background: #e6a23c; }
.fc-type.date { background: #67c23a; }
.fc-type.bool { background: #909399; }
.fc-type.text { background: #409eff; }
.fc-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 画布（灰底点阵，无卡片包裹） */
.canvas-wrap {
  flex: 1; min-width: 0; position: relative; overflow-y: auto; padding: 12px;
  background-image: radial-gradient(circle, #d4d7de 1px, transparent 1px); background-size: 16px 16px;
}
.gi-card {
  height: 100%; background: #fff; border: 1px solid #e4e7ed; border-radius: 8px;
  display: flex; flex-direction: column; overflow: hidden; cursor: pointer;
}
.gi-card.selected { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64, 158, 255, .25); }
.gi-head {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-bottom: 1px solid #f0f2f5; font-size: 13px;
}
.gi-type { flex-shrink: 0; font-size: 12px; color: #fff; background: #409eff; border-radius: 4px; padding: 1px 6px; }
.gi-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.gi-ds { flex-shrink: 0; font-size: 11px; color: #909399; background: #f0f2f5; border-radius: 4px; padding: 1px 6px; }
.gi-body { flex: 1; display: flex; align-items: center; justify-content: center; color: #c0c4cc; font-size: 12px; }
/* 画布内真实渲染：压平内层卡片，避免双层阴影 */
.gi-real { flex: 1; min-height: 0; overflow: hidden; }
.gi-real :deep(.block-card), .gi-real :deep(.stat-card) { box-shadow: none; border-radius: 0; height: 100%; box-sizing: border-box; }
.gi-real :deep(.rblock), .gi-real :deep(.rblock.fill) { height: 100%; }
.panel-tip { margin-top: 8px; font-size: 12px; color: #c0c4cc; line-height: 1.5; }

.empty-hint {
  position: absolute; top: 40%; left: 50%; transform: translateX(-50%);
  color: #c0c4cc; font-size: 14px; pointer-events: none;
}

/* 右侧配置面板：浮动覆盖画布右缘（画布尺寸恒定，块不被推挤缩放），可拖宽 */
.config-panel {
  position: absolute; right: 0; top: 0; bottom: 0; z-index: 20;
  background: #fff; border-left: 1px solid #e4e7ed; box-shadow: -6px 0 20px rgba(0, 0, 0, .1);
  overflow-y: auto; padding: 12px; animation: panel-in .16s ease-out;
}
@keyframes panel-in {
  from { transform: translateX(24px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
.panel-resizer { position: absolute; left: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; z-index: 5; }
.panel-resizer:hover { background: rgba(64, 158, 255, .35); }
.config-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.config-title { font-size: 13px; font-weight: 600; }
.mb { margin-bottom: 10px; }
.w-full { width: 100%; }

.src-sec { margin-bottom: 22px; }
.src-title { font-size: 14px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; }
.join-card { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px; margin-bottom: 10px; }
.join-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cf-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.src-tip { font-size: 12px; color: #909399; line-height: 1.7; }

:deep(.vgl-item--placeholder) { background: #409eff !important; opacity: .2; }
</style>
