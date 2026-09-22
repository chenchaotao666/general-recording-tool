<template>
  <div>
    <div class="page-header">
      <h2>任务规则</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
    </div>

    <el-alert type="info" :closable="false" style="margin-bottom: 14px"
      title="任务按周期扫描数据表：条件命中的记录会触发动作（站内通知/邮件/短信/Webhook）。同一记录在冷却期内不会重复触发。建议先用「试运行」确认命中范围再启用。" />

    <el-table :data="rules" v-loading="loading" border>
      <el-table-column prop="name" label="任务名称" min-width="150" />
      <el-table-column prop="table_label" label="数据表" width="130" />
      <el-table-column label="条件" min-width="180">
        <template #default="{ row }">
          <span v-if="row.condition_mode === 'llm'" style="color: #7c3aed">
            LLM 判断：{{ row.condition.description }}
          </span>
          <span v-else>{{ conditionSummary(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="周期" width="140">
        <template #default="{ row }">{{ scheduleDesc(row.schedule) }}</template>
      </el-table-column>
      <el-table-column label="动作" width="110">
        <template #default="{ row }">
          <el-tag size="small">{{ ACTION_LABELS[row.action.type] || row.action.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近运行" width="200">
        <template #default="{ row }">
          <span v-if="row.last_run">
            {{ row.last_run.run_at }}<br />
            <span style="font-size: 12px; color: #909399">
              命中 {{ row.last_run.matched }} / 触发 {{ row.last_run.sent }} / 失败 {{ row.last_run.failed }}
            </span>
            <div v-if="row.last_run.error" style="font-size: 12px; color: #f56c6c">{{ row.last_run.error }}</div>
          </span>
          <span v-else style="color: #c0c4cc">未运行</span>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="70" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="toggle(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250">
        <template #default="{ row }">
          <el-button text size="small" :loading="testingId === row.id" @click="test(row)">试运行</el-button>
          <el-button text size="small" type="success" :loading="runningId === row.id" @click="run(row)">立即执行</el-button>
          <el-button text size="small" @click="showRuns(row)">日志</el-button>
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确定删除该任务？" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>还没有任务，点击右上角新建</template>
    </el-table>

    <!-- 任务编辑器 -->
    <el-dialog v-model="editorVisible" :title="editing ? '编辑任务' : '新建任务'" width="820px" destroy-on-close>
      <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 10px">
        <el-button size="small" type="warning" plain :icon="MagicStick" @click="openAiAssist">AI 辅助生成</el-button>
        <span style="font-size: 12px; color: #909399">用自然语言描述需求，AI 自动生成条件、周期和动作配置</span>
      </div>
      <el-form label-width="100px">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="如：超过30天未跟进提醒" style="width: 400px" />
        </el-form-item>
        <el-form-item label="数据表" required>
          <el-select v-model="form.table_id" style="width: 400px" @change="onTableChange">
            <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="判断方式">
          <el-radio-group v-model="form.condition_mode">
            <el-radio value="structured">结构化条件</el-radio>
            <el-radio value="llm">LLM 智能判断</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 结构化条件 -->
        <el-form-item v-if="form.condition_mode === 'structured'" label="条件">
          <div class="cond-box">
            <el-radio-group v-model="form.condition.logic" size="small" style="margin-bottom: 8px">
              <el-radio value="AND">满足全部条件</el-radio>
              <el-radio value="OR">满足任一条件</el-radio>
            </el-radio-group>
            <div v-for="(r, i) in form.condition.rules" :key="i" class="cond-row">
              <el-select v-model="r.field" placeholder="字段" style="width: 150px" @change="r.value = null">
                <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
                <el-option label="创建时间" value="created_at" />
                <el-option label="更新时间" value="updated_at" />
              </el-select>
              <el-select v-model="r.op" placeholder="操作" style="width: 150px">
                <el-option v-for="[v, l] in opsFor(r.field)" :key="v" :label="l" :value="v" />
              </el-select>
              <template v-if="!NO_VALUE_OPS.includes(r.op)">
                <el-input-number
                  v-if="DAY_OPS.includes(r.op)" v-model="r.value" :min="0" controls-position="right" style="width: 120px"
                />
                <el-select
                  v-else-if="fieldOf(r.field)?.widget === 'select'"
                  v-model="r.value" :multiple="r.op === 'in'" clearable style="width: 200px"
                >
                  <el-option v-for="o in selectOptions(fieldOf(r.field))" :key="String(o)" :label="o" :value="o" />
                </el-select>
                <el-select v-else-if="fieldOf(r.field)?.data_type === 'bool'" v-model="r.value" style="width: 100px">
                  <el-option label="是" :value="true" /><el-option label="否" :value="false" />
                </el-select>
                <el-date-picker
                  v-else-if="['date', 'datetime'].includes(fieldOf(r.field)?.data_type)"
                  v-model="r.value" type="date" value-format="YYYY-MM-DD" style="width: 160px"
                />
                <el-input-number
                  v-else-if="['int', 'decimal'].includes(fieldOf(r.field)?.data_type)"
                  v-model="r.value" controls-position="right" style="width: 150px"
                />
                <el-input v-else v-model="r.value" style="width: 200px" />
              </template>
              <span v-if="DAY_OPS.includes(r.op)" style="color: #909399; font-size: 12px">天</span>
              <el-button text type="danger" size="small" @click="form.condition.rules.splice(i, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="form.condition.rules.push({ field: null, op: 'eq', value: null })">
              添加条件
            </el-button>
          </div>
        </el-form-item>

        <!-- LLM 判断 -->
        <el-form-item v-else label="条件描述" required>
          <div style="width: 100%">
            <el-input
              v-model="form.condition.description" type="textarea" :rows="3"
              placeholder="用自然语言描述判断条件，如：超过1个月没有跟进且意向金额大于1万的客户"
            />
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              每次执行时由大模型逐条判断（每次最多扫描 200 条候选记录），成本高于结构化条件。
            </div>
          </div>
        </el-form-item>

        <el-form-item label="执行周期" required>
          <el-radio-group v-model="form.schedule.type">
            <el-radio value="interval">每隔</el-radio>
            <el-radio value="cron">cron 表达式</el-radio>
          </el-radio-group>
          <template v-if="form.schedule.type === 'interval'">
            <el-input-number v-model="form.schedule.minutes" :min="1" controls-position="right" style="margin: 0 8px; width: 120px" />
            分钟
          </template>
          <template v-else>
            <el-input v-model="form.schedule.expr" style="width: 180px; margin: 0 8px" placeholder="分 时 日 月 周" />
            <el-select style="width: 150px" placeholder="常用预设" @change="(v) => { form.schedule.expr = v }">
              <el-option label="每小时" value="0 * * * *" />
              <el-option label="每天 9 点" value="0 9 * * *" />
              <el-option label="每天 9 点半" value="30 9 * * *" />
              <el-option label="每周一 9 点" value="0 9 * * 1" />
            </el-select>
          </template>
        </el-form-item>

        <el-form-item label="动作" required>
          <div style="width: 100%">
            <el-radio-group v-model="form.action.type">
              <el-radio value="notify">站内通知</el-radio>
              <el-radio value="email">邮件</el-radio>
              <el-radio value="sms">短信</el-radio>
              <el-radio value="webhook">Webhook</el-radio>
            </el-radio-group>
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              邮件/短信：每次执行只发送一条，汇总所有命中记录；站内通知/Webhook：每条命中记录触发一次
            </div>
          </div>
        </el-form-item>

        <el-form-item v-if="form.action.type === 'webhook'" label="Webhook URL" required>
          <el-input v-model="form.action.webhook_url" placeholder="https://..." style="width: 480px" />
        </el-form-item>

        <el-form-item label="内容模板" required>
          <div style="width: 100%">
            <el-input
              v-model="form.action.template" type="textarea" :rows="3"
              placeholder="支持 {字段名} 占位符，如：客户【{customer_name}】已超期未跟进"
            />
            <div style="margin-top: 6px">
              <el-tag
                v-for="f in tableFields" :key="f.field_name" size="small"
                style="margin: 0 6px 4px 0; cursor: pointer"
                @click="form.action.template += `{${f.field_name}}`"
              >{{ f.label }}</el-tag>
            </div>
          </div>
        </el-form-item>

        <el-form-item v-if="form.action.type === 'email' || form.action.type === 'sms'" label="接收人">
          <el-radio-group v-model="form.action.recipients.type">
            <el-radio value="fixed">固定地址</el-radio>
            <el-radio value="field">取自记录字段</el-radio>
          </el-radio-group>
          <el-input
            v-if="form.action.recipients.type === 'fixed'"
            v-model="form.action.recipients.value"
            :placeholder="form.action.type === 'email' ? '邮箱地址，多个用逗号分隔' : '手机号，多个用逗号分隔'"
            style="width: 320px; margin-left: 8px"
          />
          <el-select v-else v-model="form.action.recipients.field" style="width: 200px; margin-left: 8px" placeholder="选择字段">
            <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
          </el-select>
        </el-form-item>

        <el-form-item label="高级设置">
          <span style="margin-right: 6px">冷却期</span>
          <el-input-number v-model="form.cooldown_hours" :min="0" controls-position="right" style="width: 110px" />
          <span style="margin: 0 12px 0 6px">小时（0 = 同一记录永不重复）</span>
          <span style="margin-right: 6px">单次上限</span>
          <el-input-number v-model="form.max_per_run" :min="1" :max="500" controls-position="right" style="width: 110px" />
          <span style="margin-left: 6px">条</span>
        </el-form-item>

        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 试运行结果 -->
    <el-dialog v-model="testVisible" title="试运行结果（不触发动作）" width="760px">
      <el-alert
        :title="`命中 ${testResult?.matched} 条记录，其中 ${testResult?.would_fire} 条会实际触发（其余在冷却期内）`"
        type="success" :closable="false" style="margin-bottom: 12px"
      />
      <el-table v-if="testResult?.samples?.length" :data="testResult.samples" size="small" border max-height="400">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column
          v-for="f in sampleFields" :key="f.field_name" :prop="f.field_name" :label="f.label"
          show-overflow-tooltip
        />
      </el-table>
      <el-empty v-else description="当前没有命中记录" />
    </el-dialog>

    <!-- 运行日志 -->
    <el-dialog v-model="runsVisible" :title="`运行日志 - ${runsRule?.name || ''}`" width="820px">
      <el-table :data="runs" size="small" border max-height="440">
        <el-table-column type="expand">
          <template #default="{ row }">
            <pre class="detail-pre">{{ JSON.stringify(row.detail, null, 2) }}</pre>
          </template>
        </el-table-column>
        <el-table-column prop="run_at" label="时间" width="160" />
        <el-table-column label="触发方式" width="90">
          <template #default="{ row }">
            {{ { schedule: '计划', manual: '手动', test: '试运行' }[row.trigger] || row.trigger }}
          </template>
        </el-table-column>
        <el-table-column prop="matched_count" label="命中" width="70" />
        <el-table-column prop="sent_count" label="成功" width="70" />
        <el-table-column prop="fail_count" label="失败" width="70" />
        <el-table-column label="错误">
          <template #default="{ row }">
            <span v-if="row.error" style="color: #f56c6c">{{ row.error }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- AI 辅助对话框 -->
    <el-dialog v-model="aiVisible" title="AI 辅助生成任务" width="640px" append-to-body destroy-on-close>
      <el-input
        v-model="aiDescription" type="textarea" :rows="4"
        placeholder="用自然语言描述你想要的任务，如：&#10;每天早上9点检查超过30天没跟进的客户，发邮件提醒经理，内容里带上客户名称和分级"
      />
      <div style="margin: 10px 0">
        <el-button type="primary" :loading="aiGenerating" :disabled="!aiDescription.trim()" @click="aiGenerate">
          {{ aiResult ? '重新生成' : '生成' }}
        </el-button>
        <span v-if="aiGenerating" style="margin-left: 10px; font-size: 12px; color: #909399">AI 设计中，可能需要十几秒…</span>
      </div>
      <template v-if="aiResult">
        <el-alert type="success" :closable="false" style="margin-bottom: 10px">
          <template #title>已生成「{{ aiResult.name }}」</template>
        </el-alert>
        <div class="ai-summary">
          <div><b>判断方式：</b>{{ aiResult.condition_mode === 'llm' ? 'LLM 智能判断' : '结构化条件' }}</div>
          <div v-if="aiResult.condition_mode === 'llm'"><b>条件描述：</b>{{ aiResult.condition.description }}</div>
          <div v-else><b>条件：</b>{{ aiConditionSummary }}</div>
          <div><b>周期：</b>{{ aiScheduleDesc }}</div>
          <div><b>动作：</b>{{ ACTION_LABELS[aiResult.action.type] || aiResult.action.type }}</div>
          <div><b>内容：</b>{{ aiResult.action.template }}</div>
          <div><b>冷却期：</b>{{ aiResult.cooldown_hours }} 小时</div>
        </div>
        <el-alert v-if="aiResult.notes" type="warning" :closable="false" :title="aiResult.notes" style="margin-top: 10px" />
      </template>
      <template #footer>
        <el-button @click="aiVisible = false">取消</el-button>
        <el-button v-if="aiResult" type="primary" @click="applyAiResult">应用到表单</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Plus } from '@element-plus/icons-vue'
import {
  aiAssistTask, createTask, deleteTask, getTable, listTables, listTasks,
  runTask, taskRuns, testTask, toggleTask, updateTask,
} from '../api'

const ACTION_LABELS = { notify: '站内通知', email: '邮件', sms: '短信', webhook: 'Webhook' }
const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']

const OPS = {
  text: [['eq', '等于'], ['ne', '不等于'], ['contains', '包含'], ['startswith', '开头是'], ['null', '为空'], ['not_null', '不为空']],
  number: [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'], ['null', '为空'], ['not_null', '不为空']],
  date: [['eq', '等于'], ['gte', '不早于'], ['lte', '不晚于'], ['today', '当天'], ['past_days', '过去 N 天'], ['older_than_days', '早于 N 天前'], ['within_days', '未来 N 天内'], ['null', '为空'], ['not_null', '不为空']],
  bool: [['eq', '等于'], ['null', '为空'], ['not_null', '不为空']],
  select: [['eq', '等于'], ['ne', '不等于'], ['in', '属于（多选）'], ['null', '为空'], ['not_null', '不为空']],
}

const rules = ref([])
const tables = ref([])
const loading = ref(false)
const editorVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const testingId = ref(null)
const runningId = ref(null)
const testVisible = ref(false)
const testResult = ref(null)
const runsVisible = ref(false)
const runs = ref([])
const runsRule = ref(null)
const tableFields = ref([])

const blankForm = () => ({
  name: '', table_id: null, enabled: false,
  condition_mode: 'structured',
  condition: { logic: 'AND', rules: [] },
  schedule: { type: 'interval', minutes: 60, expr: '0 9 * * *' },
  action: { type: 'notify', template: '', webhook_url: '', recipients: { type: 'fixed', value: '', field: '' } },
  cooldown_hours: 24, max_per_run: 100,
})
const form = reactive(blankForm())

const sampleFields = computed(() => tableFields.value.slice(0, 6))

function fieldOf(name) {
  if (name === 'created_at' || name === 'updated_at') return { field_name: name, data_type: 'datetime', widget: 'datetime-picker' }
  if (name === 'id') return { field_name: 'id', data_type: 'int', widget: 'number' }
  return tableFields.value.find((f) => f.field_name === name)
}

function opsFor(fieldName) {
  const f = fieldOf(fieldName)
  if (!f) return OPS.text
  if (f.widget === 'select') return OPS.select
  if (f.data_type === 'bool') return OPS.bool
  if (['date', 'datetime'].includes(f.data_type)) return OPS.date
  if (['int', 'decimal'].includes(f.data_type)) return OPS.number
  return OPS.text
}

function selectOptions(f) {
  return (f?.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
}

function conditionSummary(row) {
  const rules = row.condition?.rules || []
  if (!rules.length) return '（无条件）'
  const logic = row.condition.logic === 'OR' ? ' 或 ' : ' 且 '
  return rules.map((r) => {
    const f = fieldLabel(row, r.field)
    const opLabel = Object.values(OPS).flat().find(([v]) => v === r.op)?.[1] || r.op
    const val = NO_VALUE_OPS.includes(r.op) ? '' : ` ${r.value}${DAY_OPS.includes(r.op) ? ' 天' : ''}`
    return `${f} ${opLabel}${val}`
  }).join(logic)
}

function fieldLabel(row, name) {
  // 列表接口不携带字段元数据，这里尽量用已加载的字段，否则显示字段名
  return tableFields.value.find((f) => f.field_name === name)?.label || { created_at: '创建时间', updated_at: '更新时间' }[name] || name
}

function scheduleDesc(s) {
  if (s?.type === 'interval') return `每 ${s.minutes} 分钟`
  if (s?.type === 'cron') return `cron: ${s.expr}`
  return '-'
}

async function load() {
  loading.value = true
  try {
    ;[rules.value, tables.value] = await Promise.all([listTasks(), listTables()])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function onTableChange(tid) {
  form.condition.rules = []
  tableFields.value = []
  if (tid) {
    const t = await getTable(tid)
    tableFields.value = t.fields
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, blankForm())
  tableFields.value = []
  editorVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  const c = row.condition || {}
  // 先加载字段（onTableChange 会清空 rules），再回填表单，避免条件被清空
  await onTableChange(row.table_id)
  Object.assign(form, {
    name: row.name, table_id: row.table_id, enabled: row.enabled,
    condition_mode: row.condition_mode,
    condition: row.condition_mode === 'llm'
      ? { description: c.description || '' }
      : { logic: c.logic || 'AND', rules: (c.rules || []).map((r) => ({ ...r })) },
    schedule: { type: row.schedule?.type || 'interval', minutes: row.schedule?.minutes || 60, expr: row.schedule?.expr || '0 9 * * *' },
    action: {
      type: row.action?.type || 'notify', template: row.action?.template || '',
      webhook_url: row.action?.webhook_url || '',
      recipients: { type: row.action?.recipients?.type || 'fixed', value: row.action?.recipients?.value || '', field: row.action?.recipients?.field || '' },
    },
    cooldown_hours: row.cooldown_hours ?? 24, max_per_run: row.max_per_run || 100,
  })
  editorVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写任务名称')
  if (!form.table_id) return ElMessage.warning('请选择数据表')
  const payload = {
    name: form.name.trim(),
    table_id: form.table_id,
    enabled: form.enabled,
    condition_mode: form.condition_mode,
    condition: form.condition_mode === 'llm'
      ? { description: form.condition.description || '' }
      : { logic: form.condition.logic, rules: form.condition.rules.filter((r) => r.field && r.op) },
    schedule: form.schedule.type === 'interval'
      ? { type: 'interval', minutes: form.schedule.minutes }
      : { type: 'cron', expr: form.schedule.expr },
    action: {
      type: form.action.type,
      template: form.action.template,
      webhook_url: form.action.webhook_url || undefined,
      recipients: form.action.recipients,
    },
    cooldown_hours: form.cooldown_hours,
    max_per_run: form.max_per_run,
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateTask(editing.value.id, payload)
    } else {
      await createTask(payload)
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
    await toggleTask(row.id)
    row.enabled = !row.enabled
    ElMessage.success(row.enabled ? '已启用' : '已停用')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function test(row) {
  testingId.value = row.id
  try {
    const t = await getTable(row.table_id)
    tableFields.value = t.fields
    testResult.value = await testTask(row.id)
    testVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testingId.value = null
  }
}

async function run(row) {
  runningId.value = row.id
  try {
    const res = await runTask(row.id)
    if (res.error) {
      ElMessage.error(`执行出错：${res.error}`)
    } else {
      ElMessage.success(`执行完成：命中 ${res.matched}，触发 ${res.fired}，失败 ${res.failed}`)
    }
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    runningId.value = null
  }
}

async function showRuns(row) {
  runsRule.value = row
  try {
    runs.value = await taskRuns(row.id)
    runsVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function del(row) {
  try {
    await deleteTask(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)

// ---------- AI 辅助 ----------

const aiVisible = ref(false)
const aiDescription = ref('')
const aiGenerating = ref(false)
const aiResult = ref(null)

const aiConditionSummary = computed(() => {
  const rules = aiResult.value?.condition?.rules || []
  if (!rules.length) return '（无条件）'
  const logic = aiResult.value.condition.logic === 'OR' ? ' 或 ' : ' 且 '
  return rules.map((r) => {
    const f = fieldOf(r.field)?.label || r.field
    const opLabel = Object.values(OPS).flat().find(([v]) => v === r.op)?.[1] || r.op
    const val = NO_VALUE_OPS.includes(r.op) ? '' : ` ${r.value}${DAY_OPS.includes(r.op) ? ' 天' : ''}`
    return `${f} ${opLabel}${val}`
  }).join(logic)
})

const aiScheduleDesc = computed(() => scheduleDesc(aiResult.value?.schedule))

function openAiAssist() {
  if (!form.table_id) return ElMessage.warning('请先选择数据表')
  aiResult.value = null
  aiVisible.value = true
}

async function aiGenerate() {
  aiGenerating.value = true
  try {
    aiResult.value = await aiAssistTask(form.table_id, aiDescription.value.trim())
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiGenerating.value = false
  }
}

async function applyAiResult() {
  if (form.condition.rules.length || form.condition.description) {
    try {
      await ElMessageBox.confirm('应用将覆盖当前的条件、周期和动作配置，确定继续？', 'AI 辅助', { type: 'warning' })
    } catch { return }
  }
  const r = aiResult.value
  if (!form.name.trim()) form.name = r.name
  form.condition_mode = r.condition_mode
  form.condition = r.condition_mode === 'llm'
    ? { description: r.condition.description || '' }
    : { logic: r.condition.logic, rules: r.condition.rules.map((x) => ({ ...x })) }
  form.schedule = { type: r.schedule.type, minutes: r.schedule.minutes || 60, expr: r.schedule.expr || '0 9 * * *' }
  form.action = {
    type: r.action.type,
    template: r.action.template,
    webhook_url: r.action.webhook_url || '',
    recipients: { type: 'fixed', value: '', field: '', ...(r.action.recipients || {}) },
  }
  form.cooldown_hours = r.cooldown_hours
  aiVisible.value = false
  ElMessage.success('已应用，可在下方继续调整')
}
</script>

<style scoped>
.cond-box { width: 100%; }
.cond-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.detail-pre { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.ai-summary { font-size: 13px; line-height: 2; color: #606266; }
</style>
