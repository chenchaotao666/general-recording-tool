<template>
  <el-form label-width="100px">
    <el-form-item label="报表名称" required>
      <el-input v-model="form.name" placeholder="如：客户跟进周报" style="width: 400px" />
    </el-form-item>
    <el-form-item label="描述">
      <el-input v-model="form.description" placeholder="选填" style="width: 400px" />
    </el-form-item>
    <el-form-item label="数据表" required>
      <el-select v-model="form.table_id" style="width: 400px" @change="onTableChange">
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
    </el-form-item>

    <el-form-item label="时间口径" required>
      <el-select v-model="form.range.mode" style="width: 130px">
        <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
      </el-select>
      <span style="margin: 0 6px 0 14px">按</span>
      <el-select v-model="form.range.date_field" style="width: 160px">
        <el-option label="创建时间" value="created_at" />
        <el-option label="更新时间" value="updated_at" />
        <el-option v-for="f in dateFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
      </el-select>
      <span style="margin-left: 6px; color: #909399; font-size: 12px">统计</span>
      <template v-if="form.range.mode === 'custom'">
        <el-date-picker
          v-model="customRange" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始日期" end-placeholder="结束日期" style="margin-left: 12px"
        />
      </template>
    </el-form-item>

    <el-form-item label="报表区块">
      <div class="blocks-box">
        <div style="margin-bottom: 10px; display: flex; align-items: center; gap: 10px">
          <el-button size="small" type="warning" plain :icon="MagicStick" @click="openAiAssist">AI 辅助生成</el-button>
          <span style="font-size: 12px; color: #909399">用自然语言描述需求，AI 自动生成时间口径和区块配置</span>
        </div>
        <el-alert type="info" :closable="false" style="margin-bottom: 10px"
          title="每个区块的筛选条件会在报表时间范围的基础上叠加。" />
        <el-card v-for="(b, i) in form.blocks" :key="b.id" class="block-card" shadow="never">
          <div class="block-head">
            <el-tag size="small" :type="BLOCK_TAG[b.type]">{{ BLOCK_LABELS[b.type] }}</el-tag>
            <el-input v-model="b.title" placeholder="区块标题" size="small" style="width: 220px; margin-left: 8px" />
            <span class="block-id">{{ b.id }}</span>
            <span style="flex: 1" />
            <el-button text size="small" :disabled="i === 0" @click="moveBlock(i, -1)">上移</el-button>
            <el-button text size="small" :disabled="i === form.blocks.length - 1" @click="moveBlock(i, 1)">下移</el-button>
            <el-button text type="danger" size="small" @click="form.blocks.splice(i, 1)">删除</el-button>
          </div>

          <!-- 统计卡片 -->
          <div v-if="b.type === 'stat'" class="block-body">
            <el-select v-model="b.agg" size="small" style="width: 110px" @change="onAggChange(b)">
              <el-option v-for="[v, l] in STAT_AGGS" :key="v" :label="l" :value="v" />
            </el-select>
            <el-select
              v-if="needsField(b.agg)" v-model="b.field" size="small"
              :placeholder="b.agg === 'count_distinct' ? '统计字段' : '数值字段'"
              style="width: 160px; margin-left: 8px"
            >
              <el-option v-for="f in aggFields(b.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
            <span v-if="b.agg === 'ratio'" style="margin-left: 8px; font-size: 12px; color: #909399">
              满足筛选的记录数 ÷ 口径内总数
            </span>
            <el-checkbox v-model="b.compare" style="margin-left: 12px">环比上期</el-checkbox>
          </div>

          <!-- 图表 -->
          <div v-else-if="b.type === 'chart'" class="block-body">
            <el-radio-group v-model="b.chart_type" size="small">
              <el-radio-button value="bar">柱状图</el-radio-button>
              <el-radio-button value="line">折线图</el-radio-button>
              <el-radio-button value="pie">饼图</el-radio-button>
            </el-radio-group>
            <div style="margin-top: 8px">
              <el-select v-model="b.group.kind" size="small" style="width: 120px">
                <el-option label="按字段分组" value="field" />
                <el-option label="按日" value="day" />
                <el-option label="按周" value="week" />
                <el-option label="按月" value="month" />
              </el-select>
              <el-select v-model="b.group.field" size="small" placeholder="分组字段" style="width: 160px; margin-left: 8px">
                <el-option v-for="f in groupFields(b.group.kind)" :key="f.field_name" :label="f.label" :value="f.field_name" />
              </el-select>
              <el-select v-model="b.agg" size="small" style="width: 100px; margin-left: 8px" @change="onAggChange(b)">
                <el-option v-for="[v, l] in CHART_AGGS" :key="v" :label="l" :value="v" />
              </el-select>
              <el-select
                v-if="needsField(b.agg)" v-model="b.field" size="small"
                :placeholder="b.agg === 'count_distinct' ? '统计字段' : '数值字段'"
                style="width: 140px; margin-left: 8px"
              >
                <el-option v-for="f in aggFields(b.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
              </el-select>
              <template v-if="b.chart_type === 'pie'">
                <span style="margin-left: 8px; font-size: 12px; color: #909399">前</span>
                <el-input-number v-model="b.top_n" :min="2" :max="30" size="small" controls-position="right" style="width: 80px" />
                <span style="font-size: 12px; color: #909399">项，其余合并</span>
              </template>
            </div>
          </div>

          <!-- 明细表 -->
          <div v-else-if="b.type === 'table'" class="block-body">
            <el-select v-model="b.columns" multiple size="small" placeholder="选择列" style="width: 100%">
              <el-option label="ID" value="id" />
              <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
              <el-option label="创建时间" value="created_at" />
              <el-option label="更新时间" value="updated_at" />
            </el-select>
            <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px">
              <span style="font-size: 12px; color: #909399">排序</span>
              <el-select v-model="b.sort_by" size="small" style="width: 140px" clearable placeholder="默认按ID">
                <el-option label="ID" value="id" />
                <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
                <el-option label="创建时间" value="created_at" />
                <el-option label="更新时间" value="updated_at" />
              </el-select>
              <el-select v-model="b.sort_order" size="small" style="width: 90px">
                <el-option label="降序" value="desc" /><el-option label="升序" value="asc" />
              </el-select>
              <span style="font-size: 12px; color: #909399">行数上限</span>
              <el-input-number v-model="b.limit" :min="1" :max="500" size="small" controls-position="right" style="width: 90px" />
            </div>
          </div>

          <!-- 文本 -->
          <div v-else-if="b.type === 'text'" class="block-body">
            <el-input v-model="b.content" type="textarea" :rows="2" placeholder="支持占位符：{range_label} 时间范围、{b1} 引用统计卡片的值" />
            <div style="margin-top: 6px">
              <el-tag
                v-for="s in statBlocks" :key="s.id" size="small"
                style="margin: 0 6px 4px 0; cursor: pointer"
                @click="b.content += `{${s.id}}`"
              >{{ s.title || s.id }}</el-tag>
            </div>
          </div>

          <!-- 筛选条件（stat/chart/table 共用） -->
          <div v-if="b.type !== 'text'" class="block-filters">
            <div style="font-size: 12px; color: #909399; margin-bottom: 6px">筛选（可选）</div>
            <el-radio-group v-model="b.filters.logic" size="small" style="margin-bottom: 6px">
              <el-radio value="AND">满足全部</el-radio>
              <el-radio value="OR">满足任一</el-radio>
            </el-radio-group>
            <div v-for="(r, ri) in b.filters.rules" :key="ri" class="cond-row">
              <el-select v-model="r.field" placeholder="字段" size="small" style="width: 140px" @change="r.value = null">
                <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
                <el-option label="创建时间" value="created_at" />
                <el-option label="更新时间" value="updated_at" />
              </el-select>
              <el-select v-model="r.op" placeholder="操作" size="small" style="width: 130px">
                <el-option v-for="[v, l] in opsFor(r.field)" :key="v" :label="l" :value="v" />
              </el-select>
              <template v-if="!NO_VALUE_OPS.includes(r.op)">
                <el-input-number
                  v-if="DAY_OPS.includes(r.op)" v-model="r.value" :min="0" size="small" controls-position="right" style="width: 110px"
                />
                <el-select
                  v-else-if="fieldOf(r.field)?.widget === 'select'"
                  v-model="r.value" :multiple="r.op === 'in'" clearable size="small" style="width: 180px"
                >
                  <el-option v-for="o in selectOptions(fieldOf(r.field))" :key="String(o)" :label="o" :value="o" />
                </el-select>
                <el-select v-else-if="fieldOf(r.field)?.data_type === 'bool'" v-model="r.value" size="small" style="width: 90px">
                  <el-option label="是" :value="true" /><el-option label="否" :value="false" />
                </el-select>
                <el-date-picker
                  v-else-if="['date', 'datetime'].includes(fieldOf(r.field)?.data_type)"
                  v-model="r.value" type="date" value-format="YYYY-MM-DD" size="small" style="width: 150px"
                />
                <el-input-number
                  v-else-if="['int', 'decimal'].includes(fieldOf(r.field)?.data_type)"
                  v-model="r.value" size="small" controls-position="right" style="width: 130px"
                />
                <el-input v-else v-model="r.value" size="small" style="width: 180px" />
              </template>
              <span v-if="DAY_OPS.includes(r.op)" style="color: #909399; font-size: 12px">天</span>
              <el-button text type="danger" size="small" @click="b.filters.rules.splice(ri, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="b.filters.rules.push({ field: null, op: 'eq', value: null })">添加条件</el-button>
          </div>
        </el-card>

        <el-dropdown @command="addBlock">
          <el-button size="small" type="primary" plain :icon="Plus">添加区块</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="stat">统计卡片</el-dropdown-item>
              <el-dropdown-item command="chart">图表</el-dropdown-item>
              <el-dropdown-item command="table">明细表</el-dropdown-item>
              <el-dropdown-item command="text">文本说明</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-form-item>

    <el-form-item label="查看筛选">
      <el-select v-model="form.filter_fields" multiple size="small" placeholder="选择允许查看者自助筛选的字段（可多选）" style="width: 400px">
        <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
      </el-select>
      <span style="margin-left: 10px; color: #909399; font-size: 12px">查看报表时可按这些字段自助过滤，不改动模板配置</span>
    </el-form-item>

    <el-divider content-position="left">定时推送（可选）</el-divider>
    <el-form-item label="执行周期">
      <el-radio-group v-model="form.schedule.type">
        <el-radio value="">不定时</el-radio>
        <el-radio value="interval">每隔</el-radio>
        <el-radio value="cron">cron 表达式</el-radio>
      </el-radio-group>
      <template v-if="form.schedule.type === 'interval'">
        <el-input-number v-model="form.schedule.minutes" :min="1" controls-position="right" style="margin: 0 8px; width: 120px" />
        分钟
      </template>
      <template v-else-if="form.schedule.type === 'cron'">
        <el-input v-model="form.schedule.expr" style="width: 180px; margin: 0 8px" placeholder="分 时 日 月 周" />
        <el-select style="width: 160px" placeholder="常用预设" @change="(v) => { form.schedule.expr = v }">
          <el-option label="每天 9 点" value="0 9 * * *" />
          <el-option label="每周一 9 点（周报）" value="0 9 * * 1" />
          <el-option label="每月 1 号 9 点（月报）" value="0 9 1 * *" />
        </el-select>
      </template>
    </el-form-item>
    <template v-if="form.schedule.type">
      <el-form-item label="收件邮箱" required>
        <el-input v-model="form.push.recipients" placeholder="多个用逗号分隔" style="width: 400px" />
      </el-form-item>
      <el-form-item label="推送内容">
        <el-checkbox-group v-model="form.push.formats">
          <el-checkbox value="html_inline">邮件正文（统计+数据表）</el-checkbox>
          <el-checkbox value="xlsx">Excel 附件（含图表）</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="邮件主题">
        <el-input v-model="form.push.subject" placeholder="默认：【报表名】时间范围" style="width: 400px" />
      </el-form-item>
      <el-form-item label="启用推送">
        <el-switch v-model="form.enabled" />
      </el-form-item>
    </template>
  </el-form>

  <!-- AI 辅助对话框 -->
  <el-dialog v-model="aiVisible" title="AI 辅助生成报表" width="640px" append-to-body destroy-on-close>
    <el-input
      v-model="aiDescription" type="textarea" :rows="4"
      placeholder="用自然语言描述你想要的报表，如：&#10;做一个上周的客户跟进周报，包含新增客户数、客户分级占比、每日新增趋势、客户明细和一段小结"
    />
    <div style="margin: 10px 0">
      <el-button type="primary" :loading="aiGenerating" :disabled="!aiDescription.trim()" @click="aiGenerate">
        {{ aiResult ? '重新生成' : '生成' }}
      </el-button>
      <span v-if="aiGenerating" style="margin-left: 10px; font-size: 12px; color: #909399">AI 设计中，可能需要十几秒…</span>
    </div>
    <template v-if="aiResult">
      <el-alert type="success" :closable="false" style="margin-bottom: 10px">
        <template #title>
          已生成「{{ aiResult.name }}」：{{ aiRangeDesc }}，{{ aiResult.blocks.length }} 个区块
        </template>
      </el-alert>
      <div class="ai-preview">
        <div v-for="b in aiResult.blocks" :key="b.id" class="ai-preview-row">
          <el-tag size="small" :type="BLOCK_TAG[b.type]">{{ BLOCK_LABELS[b.type] }}</el-tag>
          <span style="margin-left: 8px">{{ b.title }}</span>
          <span style="margin-left: 8px; font-size: 12px; color: #909399">{{ blockDesc(b) }}</span>
        </div>
      </div>
      <el-alert v-if="aiResult.notes" type="warning" :closable="false" :title="aiResult.notes" style="margin-top: 10px" />
    </template>
    <template #footer>
      <el-button @click="aiVisible = false">取消</el-button>
      <el-button v-if="aiResult" type="primary" @click="applyAiResult">应用到表单</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Plus } from '@element-plus/icons-vue'
import { aiAssistReport, getTable } from '../api'

const props = defineProps({ form: { type: Object, required: true }, tables: { type: Array, default: () => [] } })

const BLOCK_LABELS = { stat: '统计卡片', chart: '图表', table: '明细表', text: '文本' }
const BLOCK_TAG = { stat: 'success', chart: 'primary', table: 'warning', text: 'info' }
const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]
const STAT_AGGS = [
  ['count', '计数'], ['count_distinct', '去重计数'], ['sum', '求和'],
  ['avg', '平均值'], ['max', '最大值'], ['min', '最小值'], ['ratio', '占比%'],
]
const CHART_AGGS = STAT_AGGS.filter(([v]) => v !== 'ratio')
const NO_VALUE_OPS = ['null', 'not_null', 'today']
const DAY_OPS = ['older_than_days', 'within_days', 'past_days']
const OPS = {
  text: [['eq', '等于'], ['ne', '不等于'], ['contains', '包含'], ['startswith', '开头是'], ['null', '为空'], ['not_null', '不为空']],
  number: [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['gte', '至少'], ['lt', '小于'], ['lte', '至多'], ['null', '为空'], ['not_null', '不为空']],
  date: [['eq', '等于'], ['gte', '不早于'], ['lte', '不晚于'], ['today', '当天'], ['past_days', '过去 N 天'], ['older_than_days', '早于 N 天前'], ['within_days', '未来 N 天内'], ['null', '为空'], ['not_null', '不为空']],
  bool: [['eq', '等于'], ['null', '为空'], ['not_null', '不为空']],
  select: [['eq', '等于'], ['ne', '不等于'], ['in', '属于（多选）'], ['null', '为空'], ['not_null', '不为空']],
}

const tableFields = ref([])

// 自定义日期范围：daterange 需要数组，映射到 range.start/end
const customRange = computed({
  get: () => (props.form.range.start && props.form.range.end ? [props.form.range.start, props.form.range.end] : null),
  set: (v) => {
    props.form.range.start = v?.[0] || null
    props.form.range.end = v?.[1] || null
  },
})

const dateFields = computed(() => tableFields.value.filter((f) => ['date', 'datetime'].includes(f.data_type)))
const numericFields = computed(() => tableFields.value.filter((f) => ['int', 'decimal'].includes(f.data_type)))
const statBlocks = computed(() => props.form.blocks.filter((b) => b.type === 'stat'))

function needsField(agg) {
  return agg !== 'count' && agg !== 'ratio'
}

function aggFields(agg) {
  // 去重计数可用任意字段；其余数值聚合只能选数值字段
  return agg === 'count_distinct' ? tableFields.value : numericFields.value
}

function onAggChange(b) {
  if (!needsField(b.agg)) b.field = null
}

function groupFields(kind) {
  const sys = [
    { field_name: 'created_at', label: '创建时间' },
    { field_name: 'updated_at', label: '更新时间' },
  ]
  if (kind === 'field') return [...tableFields.value]
  return [...dateFields.value, ...sys]
}

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
  // 与任务条件一致：选项存的是 value
  return (f?.options?.options || []).map((o) => (typeof o === 'object' ? o.value : o))
}

let blockSeq = 0
function nextBlockId() {
  const existing = new Set(props.form.blocks.map((b) => b.id))
  do { blockSeq += 1 } while (existing.has(`b${blockSeq}`))
  return `b${blockSeq}`
}

function addBlock(type) {
  const base = { id: nextBlockId(), type, title: '', filters: { logic: 'AND', rules: [] } }
  if (type === 'stat') Object.assign(base, { agg: 'count', field: null })
  if (type === 'chart') Object.assign(base, { chart_type: 'bar', group: { kind: 'field', field: null }, agg: 'count', field: null, top_n: 8 })
  if (type === 'table') Object.assign(base, { columns: [], sort_by: 'created_at', sort_order: 'desc', limit: 100 })
  if (type === 'text') Object.assign(base, { content: '' })
  props.form.blocks.push(base)
}

function moveBlock(i, dir) {
  const arr = props.form.blocks
  const [b] = arr.splice(i, 1)
  arr.splice(i + dir, 0, b)
}

async function onTableChange(tid) {
  tableFields.value = []
  if (tid) {
    const t = await getTable(tid)
    tableFields.value = t.fields
  }
}

// 打开编辑时父组件会设置 form.table_id，这里加载字段
watch(() => props.form.table_id, (tid) => { if (tid && !tableFields.value.length) onTableChange(tid) }, { immediate: true })

// ---------- AI 辅助 ----------

const aiVisible = ref(false)
const aiDescription = ref('')
const aiGenerating = ref(false)
const aiResult = ref(null)

const RANGE_MODE_TEXT = Object.fromEntries(RANGE_MODES)
const AGG_TEXT = { count: '计数', count_distinct: '去重计数', sum: '求和', avg: '平均', max: '最大', min: '最小', ratio: '占比%' }
const CHART_TEXT = { bar: '柱状图', line: '折线图', pie: '饼图' }
const GROUP_TEXT = { field: '按字段', day: '按日', week: '按周', month: '按月' }

const aiRangeDesc = computed(() => {
  const r = aiResult.value?.range || {}
  const df = fieldOf(r.date_field)?.label || { created_at: '创建时间', updated_at: '更新时间' }[r.date_field] || r.date_field
  return `${RANGE_MODE_TEXT[r.mode] || r.mode} · 按${df}统计`
})

function blockDesc(b) {
  if (b.type === 'stat') return AGG_TEXT[b.agg] + (b.field ? `（${fieldOf(b.field)?.label || b.field}）` : '')
  if (b.type === 'chart') {
    const g = b.group?.kind === 'field' ? `按 ${fieldOf(b.group.field)?.label || b.group.field}` : GROUP_TEXT[b.group?.kind]
    return `${CHART_TEXT[b.chart_type]} · ${g} · ${AGG_TEXT[b.agg]}`
  }
  if (b.type === 'table') return `${(b.columns || []).length} 列 · 上限 ${b.limit} 行`
  return (b.content || '').slice(0, 40)
}

function openAiAssist() {
  if (!props.form.table_id) return ElMessage.warning('请先选择数据表')
  aiResult.value = null
  aiVisible.value = true
}

async function aiGenerate() {
  aiGenerating.value = true
  try {
    aiResult.value = await aiAssistReport(props.form.table_id, aiDescription.value.trim())
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiGenerating.value = false
  }
}

async function applyAiResult() {
  if (props.form.blocks.length) {
    try {
      await ElMessageBox.confirm('应用将覆盖当前的时间口径和全部区块配置，确定继续？', 'AI 辅助', { type: 'warning' })
    } catch { return }
  }
  if (!props.form.name.trim()) props.form.name = aiResult.value.name
  props.form.range = { mode: aiResult.value.range.mode, date_field: aiResult.value.range.date_field, start: null, end: null }
  props.form.blocks = aiResult.value.blocks.map((b) => ({ ...b, filters: b.filters || { logic: 'AND', rules: [] }, group: b.group ? { ...b.group } : undefined }))
  aiVisible.value = false
  ElMessage.success('已应用，可在下方继续调整')
}
</script>

<style scoped>
.blocks-box { width: 100%; }
.block-card { margin-bottom: 10px; }
.block-head { display: flex; align-items: center; margin-bottom: 8px; }
.block-id { font-size: 12px; color: #c0c4cc; margin-left: 8px; }
.block-body { margin-bottom: 8px; }
.block-filters { border-top: 1px dashed #e4e7ed; padding-top: 8px; }
.cond-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ai-preview { max-height: 260px; overflow-y: auto; }
.ai-preview-row { padding: 6px 0; border-bottom: 1px dashed #e4e7ed; display: flex; align-items: center; }
</style>
