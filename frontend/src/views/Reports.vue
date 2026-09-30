<template>
  <div>
    <div class="page-header">
      <h2>报表</h2>
      <div>
        <el-button @click="openTemplates">模板市场</el-button>
        <el-button class="ai-btn" :icon="MagicStick" @click="openAi">AI 生成</el-button>
        <el-button type="primary" :icon="Plus" @click="createVisible = true">新建报表</el-button>
      </div>
    </div>

    <!-- AI 生成：选表 + 一句话需求 → 生成配置 → 创建并进设计器 -->
    <el-dialog v-model="aiVisible" title="AI 生成报表" width="640px" destroy-on-close>
      <el-select v-model="aiTableId" placeholder="基于哪张表生成" style="width: 100%; margin-bottom: 10px" filterable>
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <el-input
        v-model="aiDescription" type="textarea" :rows="4"
        placeholder="用自然语言描述你想要的报表，如：做一个上周的客户跟进周报，包含新增客户数、客户分级占比、每日新增趋势、客户明细和一段小结"
      />
      <div style="margin: 10px 0">
        <el-button class="ai-btn" :loading="aiGenerating" :disabled="!aiTableId || !aiDescription.trim()" @click="aiGenerate">
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
        <el-button v-if="aiResult" class="ai-btn" :loading="aiCreating" @click="aiCreate">创建并进入设计器</el-button>
      </template>
    </el-dialog>

    <!-- 模板市场对话框（与工作流模板市场同一交互：搜索/分类/一键安装） -->
    <el-dialog v-model="tplVisible" title="模板市场 · 一键安装场景报表" width="720px">
      <div class="tpl-filter">
        <el-input v-model="tplKw" placeholder="搜索模板名称 / 描述 / 场景" clearable size="small" class="tpl-search" />
        <el-select v-model="tplCat" placeholder="全部分类" clearable size="small" style="width: 140px">
          <el-option v-for="c in tplCategories" :key="c" :label="c" :value="c" />
        </el-select>
      </div>
      <div class="tpl-grid" v-loading="tplLoading">
        <el-card v-for="t in filteredTemplates" :key="t.key" shadow="hover" class="tpl-card">
          <div class="tpl-name">
            {{ t.name }}
            <el-tag v-if="t.category" size="small" effect="plain" type="warning" class="tpl-cat">{{ t.category }}</el-tag>
          </div>
          <div class="tpl-desc">{{ t.description }}</div>
          <div class="tpl-scenario">{{ t.scenario }}</div>
          <div class="tpl-tables">
            <span v-for="tb in t.tables" :key="tb.label" class="tpl-table">
              <el-tag size="small" :type="tb.exists ? 'success' : 'info'" effect="plain">
                {{ tb.label }}{{ tb.exists ? '（已有，复用）' : '（将自动创建）' }}
              </el-tag>
            </span>
          </div>
          <el-button type="primary" size="small" @click="onInstall(t)">
            安装到我的报表
          </el-button>
        </el-card>
      </div>
      <el-empty v-if="!tplLoading && !filteredTemplates.length" description="没有匹配的模板" />
    </el-dialog>

    <!-- 安装确认：明确让用户选择是否要示例数据 -->
    <el-dialog v-model="confirmVisible" :title="`安装「${installTarget?.name || ''}」`" width="440px" append-to-body>
      <div class="cf-tables">
        <span v-for="tb in installTarget?.tables || []" :key="tb.label" class="tpl-table">
          <el-tag size="small" :type="tb.exists ? 'success' : 'info'" effect="plain">
            {{ tb.label }}{{ tb.exists ? '（已有，复用）' : '（将自动创建）' }}
          </el-tag>
        </span>
      </div>
      <el-checkbox v-model="installDemoData" class="cf-cb">
        为新建的表生成 50 条示例数据（装完即可看到真实图表）
      </el-checkbox>
      <div class="tpl-hint">复用的已有表不会写入任何数据</div>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="installing" @click="doInstall">确认安装</el-button>
      </template>
    </el-dialog>

    <el-alert type="info" :closable="false" style="margin-bottom: 14px"
      title="报表由多数据源 + 区块 + 栅格布局组成：设计器内拖字段即可成图，可配置定时推送与链接分享。" />

    <el-table :data="reports" v-loading="loading" border>
      <el-table-column prop="name" label="报表名称" min-width="90">
        <template #default="{ row }">
          <div>{{ row.name }}</div>
          <div v-if="row.description" style="font-size: 12px; color: #909399">{{ row.description }}</div>
        </template>
      </el-table-column>
      <el-table-column label="数据源" width="150">
        <template #default="{ row }">
          <template v-if="row.datasets?.length">
            {{ row.datasets[0].name || row.table_label }}
            <span v-if="row.datasets.length > 1" style="color: #909399"> 等 {{ row.datasets.length }} 个</span>
          </template>
          <template v-else>{{ row.table_label }}</template>
        </template>
      </el-table-column>
      <el-table-column label="默认口径" width="90">
        <template #default="{ row }">{{ row.range_desc }}</template>
      </el-table-column>
      <el-table-column label="区块" width="70" align="center">
        <template #default="{ row }">{{ row.block_count }}</template>
      </el-table-column>
      <el-table-column label="定时推送" width="170">
        <template #default="{ row }">
          <template v-if="row.schedule?.type">
            {{ scheduleDesc(row.schedule) }}
            <div v-if="row.last_run" style="font-size: 12px; color: #909399">
              上次推送 {{ row.last_run.run_at }}
              <span v-if="row.last_run.error" style="color: #f56c6c">失败</span>
            </div>
          </template>
          <span v-else style="color: #c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="推送" width="70" align="center">
        <template #default="{ row }">
          <el-switch v-if="row.schedule?.type" :model-value="row.enabled" @change="toggle(row)" />
          <span v-else style="color: #c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="630">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="$router.push(`/reports/${row.id}/view`)">查看</el-button>
          <el-button text type="primary" size="small" @click="$router.push(`/reports/${row.id}/layout`)">设计</el-button>
          <el-button text size="small" @click="exportFile(row, 'xlsx')">导出Excel</el-button>
          <el-button text size="small" @click="exportFile(row, 'html')">导出HTML</el-button>
          <el-button v-if="row.schedule?.type" text size="small" :loading="pushingId === row.id" @click="push(row)">推送</el-button>
          <el-button v-if="row.schedule?.type" text size="small" @click="showRuns(row)">日志</el-button>
          <el-button text size="small" @click="openShare(row)">分享</el-button>
          <el-button text size="small" @click="duplicate(row)">复制</el-button>
          <el-popconfirm title="确定删除该报表模板？" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>还没有报表，点击右上角新建</template>
    </el-table>

    <!-- 新建：名称 + 初始数据源，创建后直进设计器 -->
    <el-dialog v-model="createVisible" title="新建报表" width="440px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="如：经营周报" />
        </el-form-item>
        <el-form-item label="数据源" required>
          <el-select v-model="createForm.table_ids" multiple collapse-tags :max-collapse-tags="2"
            placeholder="选择数据表（可多选，之后也可再加）" style="width: 100%" filterable>
            <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">创建并设计</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runsVisible" :title="`推送日志 - ${runsTpl?.name || ''}`" width="720px">
      <el-table :data="runs" size="small" border max-height="440">
        <el-table-column prop="run_at" label="时间" width="160" />
        <el-table-column label="触发方式" width="90">
          <template #default="{ row }">{{ { schedule: '计划', manual: '手动' }[row.trigger] || row.trigger }}</template>
        </el-table-column>
        <el-table-column prop="range_label" label="口径" width="200" />
        <el-table-column label="发送" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.skipped" size="small" type="info" effect="plain">条件未满足</el-tag>
            <template v-else>{{ row.sent_count }}</template>
          </template>
        </el-table-column>
        <el-table-column label="错误">
          <template #default="{ row }">
            <span v-if="row.error" style="color: #f56c6c">{{ row.error }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 链接分享 -->
    <el-dialog v-model="shareVisible" :title="`分享「${shareTpl?.name}」`" width="680px">
      <el-form inline @submit.prevent>
        <el-form-item>
          <el-input v-model="linkForm.password" placeholder="访问密码（可选）" style="width: 160px" show-password />
        </el-form-item>
        <el-form-item>
          <el-input-number v-model="linkForm.expires_in_days" :min="1" :max="365" placeholder="有效期" style="width: 130px" />
          <span style="margin-left: 6px; color: #909399">天（留空永久）</span>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="linkForm.allow_interact">允许查看者筛选 / 切换时间口径</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="linkSaving" @click="createLink">生成链接</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="links" size="small" border>
        <el-table-column label="链接" min-width="280">
          <template #default="{ row }"><span style="font-size: 12px; color: #409eff; word-break: break-all">{{ linkUrl(row.token) }}</span></template>
        </el-table-column>
        <el-table-column label="密码" width="70" align="center">
          <template #default="{ row }">{{ row.has_password ? '有' : '—' }}</template>
        </el-table-column>
        <el-table-column label="交互" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.allow_interact" size="small" type="success" effect="plain">可筛选</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="有效期至" width="150">
          <template #default="{ row }">{{ row.expires_at || '永久' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="copyLink(row)">复制</el-button>
            <el-button text type="danger" size="small" @click="removeLink(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!links.length" style="color: #c0c4cc; font-size: 13px; text-align: center; padding: 20px 0">
        还没有分享链接，生成后任何人凭链接可只读查看此报表
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Plus } from '@element-plus/icons-vue'
import {
  aiAssistReport, createReport, createReportShareLink, deleteReport, deleteReportShareLink, duplicateReport,
  installReportTemplate, listReportShareLinks, listReportTemplates,
  listReports, listTables, reportExportUrl, reportRuns, testPushReport, toggleReport,
} from '../api'

const router = useRouter()
const reports = ref([])
const tables = ref([])
const loading = ref(false)
const pushingId = ref(null)
const runsVisible = ref(false)
const runs = ref([])
const runsTpl = ref(null)

function scheduleDesc(s) {
  if (s?.type === 'interval') return `每 ${s.minutes} 分钟`
  if (s?.type === 'cron') return `cron: ${s.expr}`
  return '-'
}

async function load() {
  loading.value = true
  try {
    ;[reports.value, tables.value] = await Promise.all([listReports(), listTables()])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// ---------- 新建（直进设计器） ----------
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', table_ids: [] })

async function create() {
  if (!createForm.name.trim()) return ElMessage.warning('请填写报表名称')
  if (!createForm.table_ids.length) return ElMessage.warning('请选择数据源')
  creating.value = true
  try {
    // 每张选中的表各建一个数据源（d1/d2/...），table_id 取第一张兼容旧字段
    const datasets = createForm.table_ids.map((tid, i) => {
      const t = tables.value.find((x) => x.id === tid)
      return { id: `d${i + 1}`, name: t?.label || '', base_table_id: tid, joins: [], computed_fields: [] }
    })
    const res = await createReport({
      name: createForm.name.trim(),
      table_id: createForm.table_ids[0],
      range: { mode: 'this_week' },
      datasets,
      blocks: [],
      layout: null,
      filter_fields: [],
      schedule: {},
      push: {},
    })
    createVisible.value = false
    createForm.name = ''
    createForm.table_ids = []
    router.push(`/reports/${res.id}/layout`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

// ---------- AI 生成（列表页直生成 → 创建 → 进设计器） ----------
const aiVisible = ref(false)
const aiTableId = ref(null)
const aiDescription = ref('')
const aiGenerating = ref(false)
const aiCreating = ref(false)
const aiResult = ref(null)

function openAi() {
  aiResult.value = null
  aiTableId.value = tables.value[0]?.id || null
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

async function aiCreate() {
  // 与设计器 aiApply 同一套映射：单数据源 d1、块级日期字段取 AI 建议
  aiCreating.value = true
  try {
    const t = tables.value.find((x) => x.id === aiTableId.value)
    const df = aiResult.value.range?.date_field || 'created_at'
    const blocks = aiResult.value.blocks.map((b) => ({
      ...b,
      filters: b.filters || { logic: 'AND', rules: [] },
      group: b.group ? { ...b.group } : undefined,
      dataset_id: 'd1',
      date_field: df,
      ...(b.type === 'pivot' ? {
        row: { kind: 'field', field: null, ...(b.row || {}) },
        col: { kind: 'field', field: null, ...(b.col || {}) },
        totals: b.totals !== false,
      } : {}),
    }))
    const res = await createReport({
      name: aiResult.value.name || 'AI 报表',
      table_id: aiTableId.value,
      range: { mode: aiResult.value.range?.mode || 'this_week' },
      datasets: [{ id: 'd1', name: t?.label || '', base_table_id: aiTableId.value, joins: [], computed_fields: [] }],
      blocks,
      layout: null,   // 设计器打开时自动排版
      filter_fields: [],
      schedule: {},
      push: {},
    })
    aiVisible.value = false
    ElMessage.success(`已创建「${res.name}」`)
    router.push(`/reports/${res.id}/layout`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiCreating.value = false
  }
}

// ---------- 模板市场 ----------
const tplVisible = ref(false)
const tplLoading = ref(false)
const templates = ref([])
const tplKw = ref('')
const tplCat = ref('')
const installing = ref(false)
const confirmVisible = ref(false)
const installTarget = ref(null)
const installDemoData = ref(true)   // 默认生成示例数据，每次安装时都会弹出确认框让用户选

const tplCategories = computed(() => [...new Set(templates.value.map((t) => t.category).filter(Boolean))])
const filteredTemplates = computed(() => {
  const k = tplKw.value.trim().toLowerCase()
  return templates.value.filter((t) => {
    if (tplCat.value && t.category !== tplCat.value) return false
    if (k && !(`${t.name} ${t.description} ${t.scenario}`.toLowerCase().includes(k))) return false
    return true
  })
})

async function openTemplates() {
  tplVisible.value = true
  tplLoading.value = true
  try { templates.value = await listReportTemplates() } finally { tplLoading.value = false }
}

function onInstall(t) {
  installTarget.value = t
  installDemoData.value = true
  confirmVisible.value = true
}

async function doInstall() {
  const t = installTarget.value
  if (!t) return
  installing.value = true
  try {
    const res = await installReportTemplate(t.key, installDemoData.value)
    confirmVisible.value = false
    tplVisible.value = false
    await load()
    await ElMessageBox.alert(
      res.notes || '已安装',
      `已安装「${res.name}」`,
      { confirmButtonText: '去设计器查看' },
    )
    router.push(`/reports/${res.report_id}/layout`)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || e)
  } finally {
    installing.value = false
  }
}

// ---------- 复制 ----------
async function duplicate(row) {
  try {
    const res = await duplicateReport(row.id)
    ElMessage.success(`已复制为「${res.name}」（推送配置未复制，需要请到副本里重新设置）`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggle(row) {
  try {
    await toggleReport(row.id)
    row.enabled = !row.enabled
    ElMessage.success(row.enabled ? '已启用推送' : '已停用推送')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function exportFile(row, format) {
  window.open(reportExportUrl(row.id, { format }), '_blank')
}

async function push(row) {
  pushingId.value = row.id
  try {
    const res = await testPushReport(row.id)
    ElMessage.success(`已推送 ${res.sent} 个收件人（${res.range_label}）`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    pushingId.value = null
  }
}

async function showRuns(row) {
  runsTpl.value = row
  try {
    runs.value = await reportRuns(row.id)
    runsVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function del(row) {
  try {
    await deleteReport(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 链接分享 ----------
const shareVisible = ref(false)
const shareTpl = ref(null)
const links = ref([])
const linkSaving = ref(false)
const linkForm = reactive({ password: '', expires_in_days: null, allow_interact: false })

function linkUrl(token) {
  return `${location.origin}/share/${token}`
}

async function openShare(row) {
  shareTpl.value = row
  shareVisible.value = true
  linkForm.password = ''
  linkForm.expires_in_days = null
  linkForm.allow_interact = false
  await loadLinks()
}

async function loadLinks() {
  try {
    links.value = await listReportShareLinks(shareTpl.value.id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function createLink() {
  linkSaving.value = true
  try {
    await createReportShareLink(shareTpl.value.id, {
      password: linkForm.password || null,
      expires_in_days: linkForm.expires_in_days || null,
      allow_interact: linkForm.allow_interact,
    })
    ElMessage.success('链接已生成')
    linkForm.password = ''
    linkForm.expires_in_days = null
    linkForm.allow_interact = false
    await loadLinks()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    linkSaving.value = false
  }
}

async function copyLink(row) {
  try {
    await navigator.clipboard.writeText(linkUrl(row.token))
    ElMessage.success('链接已复制')
  } catch {
    ElMessage.info(linkUrl(row.token))
  }
}

async function removeLink(row) {
  try {
    await deleteReportShareLink(shareTpl.value.id, row.id)
    ElMessage.success('已撤销')
    await loadLinks()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
/* 模板市场（与工作流列表页同款卡片网格） */
.tpl-filter { display: flex; gap: 10px; margin-bottom: 12px; }
.tpl-search { flex: 1; }
.tpl-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tpl-card { font-size: 13px; }
.tpl-name { font-weight: 600; margin-bottom: 4px; }
.tpl-cat { margin-left: 6px; }
.tpl-desc { color: #606266; margin-bottom: 6px; }
.tpl-scenario { font-size: 12px; color: #909399; margin-bottom: 8px; }
.tpl-tables { margin-bottom: 10px; display: flex; gap: 6px; flex-wrap: wrap; }
.cf-tables { margin-bottom: 12px; display: flex; gap: 6px; flex-wrap: wrap; }
.cf-cb { margin-bottom: 4px; }
.tpl-hint { font-size: 12px; color: #909399; }
</style>
