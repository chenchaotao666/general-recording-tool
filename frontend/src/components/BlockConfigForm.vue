<template>
  <!-- 单区块配置表单（设计器右侧面板专用）：标签在上、控件通栏的纵向布局。直接就地修改 block 对象。 -->
  <el-form label-position="top" size="small" class="bcf" @submit.prevent>
    <!-- 统计卡片 -->
    <template v-if="block.type === 'stat'">
      <el-form-item label="聚合方式">
        <el-select v-model="block.agg" class="w-full" @change="onAggChange(block)">
          <el-option v-for="[v, l] in STAT_AGGS" :key="v" :label="l" :value="v" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="needsField(block.agg)" :label="block.agg === 'count_distinct' ? '统计字段' : '数值字段'">
        <el-select v-model="block.field" filterable class="w-full">
          <el-option v-for="f in aggFields(block.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
        </el-select>
      </el-form-item>
      <div v-if="needsField(block.agg) && block.agg !== 'count_distinct' && !numericFields.length" class="hint">
      该数据源没有数值字段，求和/平均/最值不可用，可改用「计数」或「去重计数」
    </div>
      <div v-if="block.agg === 'ratio'" class="hint">满足筛选的记录数 ÷ 口径内总数</div>
      <el-form-item>
        <el-checkbox v-model="block.compare">环比上期</el-checkbox>
      </el-form-item>
    </template>

    <!-- 图表 -->
    <template v-else-if="block.type === 'chart'">
      <el-form-item label="图表类型">
        <el-radio-group v-model="block.chart_type" @change="onChartTypeChange">
          <el-radio-button value="bar">柱状</el-radio-button>
          <el-radio-button value="line">折线</el-radio-button>
          <el-radio-button value="area">面积</el-radio-button>
          <el-radio-button value="pie">饼图</el-radio-button>
          <el-radio-button value="gauge">仪表盘</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <!-- 仪表盘：单聚合值 + max -->
      <template v-if="block.chart_type === 'gauge'">
        <el-form-item label="聚合方式">
          <el-select v-model="block.agg" class="w-full" @change="onAggChange(block)">
            <el-option v-for="[v, l] in CHART_AGGS" :key="v" :label="l" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="needsField(block.agg)" :label="block.agg === 'count_distinct' ? '统计字段' : '数值字段'">
          <el-select v-model="block.field" filterable class="w-full">
            <el-option v-for="f in aggFields(block.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
          </el-select>
        </el-form-item>
        <div v-if="needsField(block.agg) && block.agg !== 'count_distinct' && !numericFields.length" class="hint">
      该数据源没有数值字段，求和/平均/最值不可用，可改用「计数」或「去重计数」
    </div>
        <el-form-item label="满刻度值">
          <el-input-number v-model="block.max" :min="1" controls-position="right" class="w-full" placeholder="100" />
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item label="分组方式">
          <div class="row">
            <el-select v-model="block.group.kind" style="width: 110px">
              <el-option label="按字段" value="field" />
              <el-option label="按日" value="day" />
              <el-option label="按周" value="week" />
              <el-option label="按月" value="month" />
            </el-select>
            <el-select v-model="block.group.field" filterable placeholder="分组字段" style="flex: 1">
              <el-option v-for="f in groupFields(block.group.kind)" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item v-if="seriesMode(block) !== 'metrics'" label="聚合方式">
          <div class="row">
            <el-select v-model="block.agg" style="width: 110px" @change="onAggChange(block)">
              <el-option v-for="[v, l] in CHART_AGGS" :key="v" :label="l" :value="v" />
            </el-select>
            <el-select
              v-if="needsField(block.agg)" v-model="block.field" filterable
              :placeholder="block.agg === 'count_distinct' ? '统计字段' : '数值字段'" style="flex: 1"
            >
              <el-option v-for="f in aggFields(block.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
          </div>
        </el-form-item>
        <div v-if="needsField(block.agg) && block.agg !== 'count_distinct' && !numericFields.length" class="hint">
      该数据源没有数值字段，求和/平均/最值不可用，可改用「计数」或「去重计数」
    </div>
        <el-form-item v-if="block.chart_type === 'pie'" label="取前 N 项（其余合并「其他」）">
          <el-input-number v-model="block.top_n" :min="2" :max="30" controls-position="right" class="w-full" />
        </el-form-item>
        <el-form-item v-if="block.group.kind === 'field'" label="点击图表">
          <el-select v-model="block.on_click" class="w-full">
            <el-option label="下钻查看明细" value="drill" />
            <el-option label="联动过滤其他区块" value="link" />
          </el-select>
        </el-form-item>

        <!-- 多系列 -->
        <template v-if="block.chart_type !== 'pie'">
          <el-form-item label="系列">
            <div class="row" style="align-items: center">
              <el-radio-group :model-value="seriesMode(block)" @change="(v) => setSeriesMode(block, v)">
                <el-radio-button value="single">单指标</el-radio-button>
                <el-radio-button value="metrics">多指标</el-radio-button>
                <el-radio-button value="group2">二级分组</el-radio-button>
              </el-radio-group>
              <el-checkbox v-if="seriesMode(block) !== 'single'" v-model="block.stack" style="margin-left: 10px">堆叠</el-checkbox>
            </div>
          </el-form-item>
          <template v-if="seriesMode(block) === 'metrics'">
            <div v-for="(m, mi) in block.metrics" :key="mi" class="metric-card">
              <div class="row">
                <el-select v-model="m.agg" style="width: 100px" @change="onMetricAgg(m)">
                  <el-option v-for="[v, l] in CHART_AGGS" :key="v" :label="l" :value="v" />
                </el-select>
                <el-select v-if="needsField(m.agg)" v-model="m.field" filterable placeholder="统计字段" style="flex: 1">
                  <el-option v-for="f in aggFields(m.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
                </el-select>
                <el-button text type="danger" :icon="Delete" @click="block.metrics.splice(mi, 1)" />
              </div>
              <div v-if="needsField(m.agg) && m.agg !== 'count_distinct' && !numericFields.length" class="hint" style="margin: 4px 0 0">
                该数据源没有数值字段，求和/平均/最值不可用，可改用「计数」或「去重计数」
              </div>
              <el-input v-model="m.title" placeholder="系列名（可空）" style="margin-top: 6px" />
            </div>
            <el-button
              text type="primary" :disabled="(block.metrics || []).length >= 5"
              @click="block.metrics.push({ agg: 'count', field: null, title: '' })"
            >+ 添加指标（最多 5 个）</el-button>
          </template>
          <el-form-item v-if="seriesMode(block) === 'group2'" label="二级分组字段">
            <el-select v-model="block.group2.field" filterable placeholder="该字段每个取值一个系列" class="w-full">
              <el-option v-for="f in group2Fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
            <div class="hint">取前 8 项，其余合并"其他"</div>
          </el-form-item>
        </template>
      </template>
    </template>

    <!-- 透视表 -->
    <template v-else-if="block.type === 'pivot'">
      <el-form-item label="行维度">
        <div class="row">
          <el-select v-model="block.row.kind" style="width: 100px" @change="block.row.field = null">
            <el-option label="按字段" value="field" />
            <el-option label="按日" value="day" />
            <el-option label="按周" value="week" />
            <el-option label="按月" value="month" />
          </el-select>
          <el-select v-model="block.row.field" filterable placeholder="行维度字段" style="flex: 1">
            <el-option v-for="f in groupFields(block.row.kind)" :key="f.field_name" :label="f.label" :value="f.field_name" />
          </el-select>
        </div>
      </el-form-item>
      <el-form-item label="列维度">
        <div class="row">
          <el-select v-model="block.col.kind" style="width: 100px" @change="block.col.field = null">
            <el-option label="按字段" value="field" />
            <el-option label="按日" value="day" />
            <el-option label="按周" value="week" />
            <el-option label="按月" value="month" />
          </el-select>
          <el-select v-model="block.col.field" filterable placeholder="列维度字段" style="flex: 1">
            <el-option v-for="f in groupFields(block.col.kind)" :key="f.field_name" :label="f.label" :value="f.field_name" />
          </el-select>
        </div>
      </el-form-item>
      <el-form-item label="聚合方式">
        <div class="row">
          <el-select v-model="block.agg" style="width: 110px" @change="onAggChange(block)">
            <el-option v-for="[v, l] in CHART_AGGS" :key="v" :label="l" :value="v" />
          </el-select>
          <el-select
            v-if="needsField(block.agg)" v-model="block.field" filterable
            :placeholder="block.agg === 'count_distinct' ? '统计字段' : '数值字段'" style="flex: 1"
          >
            <el-option v-for="f in aggFields(block.agg)" :key="f.field_name" :label="f.label" :value="f.field_name" />
          </el-select>
        </div>
      </el-form-item>
      <div v-if="needsField(block.agg) && block.agg !== 'count_distinct' && !numericFields.length" class="hint">
      该数据源没有数值字段，求和/平均/最值不可用，可改用「计数」或「去重计数」
    </div>
      <el-form-item>
        <el-checkbox v-model="block.totals">行列合计</el-checkbox>
      </el-form-item>
      <el-form-item v-if="block.row.kind === 'field' || block.col.kind === 'field'" label="取前 N 项（其余合并「其他」）">
        <div class="row">
          <template v-if="block.row.kind === 'field'">
            <span class="sub">行</span>
            <el-input-number v-model="block.row_top_n" :min="1" :max="100" controls-position="right" style="width: 90px" />
          </template>
          <template v-if="block.col.kind === 'field'">
            <span class="sub">列</span>
            <el-input-number v-model="block.col_top_n" :min="1" :max="20" controls-position="right" style="width: 90px" />
          </template>
        </div>
      </el-form-item>
    </template>

    <!-- 明细表 -->
    <template v-else-if="block.type === 'table'">
      <el-form-item label="展示列">
        <el-select v-model="block.columns" multiple filterable placeholder="选择列" class="w-full">
          <el-option label="ID" value="id" />
          <el-option v-for="f in fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
          <el-option label="创建时间" value="created_at" />
          <el-option label="更新时间" value="updated_at" />
        </el-select>
      </el-form-item>
      <el-form-item label="排序">
        <div class="row">
          <el-select v-model="block.sort_by" clearable filterable placeholder="默认按ID" style="flex: 1">
            <el-option label="ID" value="id" />
            <el-option v-for="f in fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
            <el-option label="创建时间" value="created_at" />
            <el-option label="更新时间" value="updated_at" />
          </el-select>
          <el-select v-model="block.sort_order" style="width: 90px">
            <el-option label="降序" value="desc" /><el-option label="升序" value="asc" />
          </el-select>
        </div>
      </el-form-item>
      <el-form-item label="行数上限">
        <el-input-number v-model="block.limit" :min="1" :max="500" controls-position="right" class="w-full" />
      </el-form-item>
    </template>

    <!-- 文本 -->
    <template v-else-if="block.type === 'text'">
      <el-form-item label="内容">
        <el-input v-model="block.content" type="textarea" :rows="3" placeholder="支持占位符：{range_label} 时间范围、{b1} 引用统计卡片的值" />
      </el-form-item>
      <el-form-item v-if="statBlocks.length" label="插入统计卡值">
        <div>
          <el-tag
            v-for="s in statBlocks" :key="s.id" size="small"
            style="margin: 0 6px 4px 0; cursor: pointer"
            @click="block.content += `{${s.id}}`"
          >{{ s.title || s.id }}</el-tag>
        </div>
      </el-form-item>
    </template>

    <!-- 筛选组件 -->
    <template v-else-if="block.type === 'filter'">
      <el-form-item label="筛选字段">
        <el-select v-model="block.field" filterable placeholder="查看报表时渲染为筛选控件" class="w-full">
          <el-option v-for="f in fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
        </el-select>
      </el-form-item>
    </template>

    <!-- 块级口径覆盖（数据类区块） -->
    <template v-if="['stat', 'chart', 'pivot', 'table'].includes(block.type)">
      <el-divider class="sec-divider" content-position="left">高级</el-divider>
      <el-form-item>
        <el-checkbox :model-value="!!block.range_override?.mode" @change="(v) => toggleRangeOverride(v)">
          覆盖全局时间口径
        </el-checkbox>
      </el-form-item>
      <template v-if="block.range_override?.mode">
        <el-form-item label="独立口径">
          <el-select v-model="block.range_override.mode" class="w-full">
            <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="block.range_override.mode === 'custom'">
          <el-date-picker
            :model-value="overrideRange" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始" end-placeholder="结束" class="w-full" @update:model-value="setOverrideRange"
          />
        </el-form-item>
      </template>
    </template>

    <!-- 筛选条件（stat/chart/pivot/table 共用） -->
    <template v-if="!['text', 'filter'].includes(block.type)">
      <el-form-item label="区块筛选（可选）">
        <el-radio-group v-model="block.filters.logic">
          <el-radio value="AND">满足全部条件</el-radio>
          <el-radio value="OR">满足任一条件</el-radio>
        </el-radio-group>
      </el-form-item>
      <div v-for="(r, ri) in block.filters.rules" :key="ri" class="rule-card">
        <div class="row">
          <el-select v-model="r.field" filterable placeholder="字段" style="flex: 1" @change="r.value = null">
            <el-option v-for="f in fields" :key="f.field_name" :label="f.label" :value="f.field_name" />
            <el-option label="创建时间" value="created_at" />
            <el-option label="更新时间" value="updated_at" />
          </el-select>
          <el-button text type="danger" :icon="Delete" @click="block.filters.rules.splice(ri, 1)" />
        </div>
        <div class="row" style="margin-top: 6px">
          <el-select v-model="r.op" placeholder="操作" style="width: 130px">
            <el-option v-for="[v, l] in opsFor(r.field)" :key="v" :label="l" :value="v" />
          </el-select>
          <template v-if="!NO_VALUE_OPS.includes(r.op)">
            <el-input-number
              v-if="DAY_OPS.includes(r.op)" v-model="r.value" :min="0" controls-position="right" style="width: 90px"
            />
            <el-select
              v-else-if="fieldOf(r.field)?.widget === 'select'"
              v-model="r.value" :multiple="r.op === 'in'" clearable style="flex: 1"
            >
              <el-option v-for="o in selectOptions(fieldOf(r.field))" :key="String(o)" :label="o" :value="o" />
            </el-select>
            <el-select v-else-if="fieldOf(r.field)?.data_type === 'bool'" v-model="r.value" style="width: 90px">
              <el-option label="是" :value="true" /><el-option label="否" :value="false" />
            </el-select>
            <el-date-picker
              v-else-if="['date', 'datetime'].includes(fieldOf(r.field)?.data_type)"
              v-model="r.value" type="date" value-format="YYYY-MM-DD" style="flex: 1"
            />
            <el-input-number
              v-else-if="['int', 'decimal'].includes(fieldOf(r.field)?.data_type)"
              v-model="r.value" controls-position="right" style="flex: 1"
            />
            <el-input v-else v-model="r.value" style="flex: 1" />
          </template>
          <span v-if="DAY_OPS.includes(r.op)" class="sub">天</span>
        </div>
      </div>
      <el-button size="small" @click="block.filters.rules.push({ field: null, op: 'eq', value: null })">+ 添加条件</el-button>
    </template>
  </el-form>
</template>

<script setup>
import { computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'

const props = defineProps({
  block: { type: Object, required: true },      // 就地修改
  fields: { type: Array, default: () => [] },   // 数据集字段（含关联/计算字段）
  statBlocks: { type: Array, default: () => [] }, // 文本占位符引用的统计卡列表
})
const block = computed(() => props.block)

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

const dateFields = computed(() => props.fields.filter((f) => ['date', 'datetime'].includes(f.data_type)))
const numericFields = computed(() => props.fields.filter((f) => ['int', 'decimal'].includes(f.data_type)))
const group2Fields = computed(() => props.fields.filter((f) => !['date', 'datetime'].includes(f.data_type)))

// 图表系列模式：series_mode 为编辑器内部显式状态（保存时剥离）；
// 旧数据没有它时按内容反推：metrics 非空 → 多指标；group2 有字段 → 二级分组；否则单指标
function seriesMode(b) {
  return b.series_mode || (b.metrics?.length ? 'metrics' : b.group2?.field ? 'group2' : 'single')
}

function setSeriesMode(b, mode) {
  b.series_mode = mode
  if (mode === 'metrics') {
    b.metrics = [{ agg: b.agg || 'count', field: b.field, title: '' }]
    b.group2 = { field: null }
  } else if (mode === 'group2') {
    b.metrics = []
    b.group2 = b.group2 || { field: null }
  } else {
    b.metrics = []
    b.group2 = { field: null }
    b.stack = false
  }
}

function onChartTypeChange(v) {
  if (v === 'pie') setSeriesMode(props.block, 'single')
  if (v === 'gauge') {
    const b = props.block
    b.metrics = []
    b.group2 = { field: null }
    b.stack = false
    b.max = b.max || 100
  }
}

function needsField(agg) {
  return agg !== 'count' && agg !== 'ratio'
}

function aggFields(agg) {
  // 去重计数可用任意字段；其余数值聚合只能选数值字段
  return agg === 'count_distinct' ? props.fields : numericFields.value
}

function onAggChange(b) {
  if (!needsField(b.agg)) b.field = null
}

// 多指标行切换聚合方式时，清空不再需要的字段
function onMetricAgg(m) {
  if (!needsField(m.agg)) m.field = null
}

function groupFields(kind) {
  const sys = [
    { field_name: 'created_at', label: '创建时间' },
    { field_name: 'updated_at', label: '更新时间' },
  ]
  if (kind === 'field') return [...props.fields]
  return [...dateFields.value, ...sys]
}

function fieldOf(name) {
  if (name === 'created_at' || name === 'updated_at') return { field_name: name, data_type: 'datetime', widget: 'datetime-picker' }
  if (name === 'id') return { field_name: 'id', data_type: 'int', widget: 'number' }
  return props.fields.find((f) => f.field_name === name)
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

// ---------- 块级口径覆盖 ----------
function toggleRangeOverride(v) {
  if (v) {
    props.block.range_override = { mode: 'this_month', start: null, end: null }
  } else {
    delete props.block.range_override
  }
}

const overrideRange = computed(() => {
  const ov = props.block.range_override
  return ov?.start && ov?.end ? [ov.start, ov.end] : null
})

function setOverrideRange(v) {
  if (!props.block.range_override) return
  props.block.range_override.start = v?.[0] || null
  props.block.range_override.end = v?.[1] || null
}
</script>

<style scoped>
.bcf :deep(.el-form-item) { margin-bottom: 12px; }
.bcf :deep(.el-form-item__label) { padding-bottom: 2px; line-height: 1.4; font-size: 12px; color: #909399; }
.w-full { width: 100%; }
.row { display: flex; align-items: center; gap: 8px; width: 100%; }
.sub { font-size: 12px; color: #909399; }
.hint { font-size: 12px; color: #c0c4cc; margin: -6px 0 10px; }
.sec-divider { margin: 18px 0 12px; }
.metric-card { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.rule-card { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; margin-bottom: 8px; background: #fafafa; }
</style>
