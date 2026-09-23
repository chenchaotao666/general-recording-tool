<template>
  <div>
    <div class="page-header">
      <h2>报表</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建报表</el-button>
    </div>

    <el-alert type="info" :closable="false" style="margin-bottom: 14px"
      title="报表模板由区块拼装：统计卡片 / 图表 / 明细表 / 文本。可在线查看、导出 Excel 或 HTML，也可配置定时邮件推送。" />

    <el-table :data="reports" v-loading="loading" border>
      <el-table-column prop="name" label="报表名称" min-width="150">
        <template #default="{ row }">
          <div>{{ row.name }}</div>
          <div v-if="row.description" style="font-size: 12px; color: #909399">{{ row.description }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="table_label" label="数据表" width="130" />
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
      <el-table-column label="操作" width="380">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="$router.push(`/reports/${row.id}/view`)">查看</el-button>
          <el-button text size="small" @click="exportFile(row, 'xlsx')">导出Excel</el-button>
          <el-button text size="small" @click="exportFile(row, 'html')">导出HTML</el-button>
          <el-button v-if="row.schedule?.type" text size="small" :loading="pushingId === row.id" @click="push(row)">推送</el-button>
          <el-button v-if="row.schedule?.type" text size="small" @click="showRuns(row)">日志</el-button>
          <el-button text size="small" @click="openShare(row)">分享</el-button>
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确定删除该报表模板？" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>还没有报表，点击右上角新建</template>
    </el-table>

    <el-dialog v-model="editorVisible" :title="editing ? '编辑报表' : '新建报表'" width="880px" destroy-on-close top="4vh">
      <ReportEditor v-if="editorVisible" :form="form" :tables="tables" />
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runsVisible" :title="`推送日志 - ${runsTpl?.name || ''}`" width="720px">
      <el-table :data="runs" size="small" border max-height="440">
        <el-table-column prop="run_at" label="时间" width="160" />
        <el-table-column label="触发方式" width="90">
          <template #default="{ row }">{{ { schedule: '计划', manual: '手动' }[row.trigger] || row.trigger }}</template>
        </el-table-column>
        <el-table-column prop="range_label" label="口径" width="200" />
        <el-table-column prop="sent_count" label="发送" width="70" />
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  createReport, createReportShareLink, deleteReport, deleteReportShareLink, listReportShareLinks,
  listReports, listTables, reportExportUrl, reportRuns, testPushReport, toggleReport, updateReport,
} from '../api'
import ReportEditor from '../components/ReportEditor.vue'

const reports = ref([])
const tables = ref([])
const loading = ref(false)
const editorVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const pushingId = ref(null)
const runsVisible = ref(false)
const runs = ref([])
const runsTpl = ref(null)

const blankForm = () => ({
  name: '', description: '', table_id: null, enabled: false,
  range: { mode: 'this_week', date_field: 'created_at', start: null, end: null },
  blocks: [],
  filter_fields: [],
  schedule: { type: '', minutes: 60, expr: '0 9 * * 1' },
  push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [] },
})
const form = reactive(blankForm())

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

function openCreate() {
  editing.value = null
  Object.assign(form, blankForm())
  editorVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name, description: row.description || '', table_id: row.table_id, enabled: row.enabled,
    range: { mode: 'this_week', date_field: 'created_at', start: null, end: null, ...(row.range || {}) },
    blocks: (row.blocks || []).map((b) => ({
      ...b,
      group: b.group ? { ...b.group } : undefined,
      filters: { logic: 'AND', ...(b.filters || {}), rules: (b.filters?.rules || []).map((r) => ({ ...r })) },
      ...(b.type === 'chart' ? { metrics: b.metrics || [], group2: b.group2 || { field: null }, stack: !!b.stack } : {}),
    })),
    filter_fields: [...(row.filter_fields || [])],
    schedule: { type: '', minutes: 60, expr: '0 9 * * 1', ...(row.schedule || {}) },
    push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [], ...(row.push || {}) },
  })
  editorVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写报表名称')
  if (!form.table_id) return ElMessage.warning('请选择数据表')
  if (!form.blocks.length) return ElMessage.warning('请至少添加一个区块')
  if (form.schedule.type && !form.push.recipients.trim()
      && !(form.push.webhooks || []).some((w) => (w.url || '').trim())) {
    return ElMessage.warning('定时推送需要至少一个推送渠道（收件邮箱或群机器人）')
  }
  const payload = {
    name: form.name.trim(),
    description: form.description || null,
    table_id: form.table_id,
    enabled: form.schedule.type ? form.enabled : false,
    range: form.range,
    blocks: form.blocks.map((b) => {
      const { series_mode, ...rest } = b  // series_mode 仅编辑器内部使用，不入库
      return {
        ...rest,
        filters: { logic: b.filters.logic, rules: (b.filters.rules || []).filter((r) => r.field && r.op) },
      }
    }),
    filter_fields: form.filter_fields || [],
    schedule: form.schedule.type === 'interval'
      ? { type: 'interval', minutes: form.schedule.minutes }
      : form.schedule.type === 'cron'
        ? { type: 'cron', expr: form.schedule.expr }
        : {},
    push: form.schedule.type
      ? { ...form.push, webhooks: (form.push.webhooks || []).filter((w) => (w.url || '').trim()) }
      : {},
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateReport(editing.value.id, payload)
    } else {
      await createReport(payload)
    }
    ElMessage.success('已保存')
    editorVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
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
const linkForm = reactive({ password: '', expires_in_days: null })

function linkUrl(token) {
  return `${location.origin}/share/${token}`
}

async function openShare(row) {
  shareTpl.value = row
  shareVisible.value = true
  linkForm.password = ''
  linkForm.expires_in_days = null
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
    })
    ElMessage.success('链接已生成')
    linkForm.password = ''
    linkForm.expires_in_days = null
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
