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
        <el-checkbox v-model="block.compare">对比</el-checkbox>
        <el-select v-if="block.compare" v-model="block.compare_type" style="margin-left: 10px; width: 150px" size="small">
          <el-option label="环比（上一期）" value="mom" />
          <el-option label="同比（去年同期）" value="yoy" />
        </el-select>
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
          <el-radio-button value="funnel">漏斗</el-radio-button>
          <el-radio-button value="mixed">组合</el-radio-button>
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
            <el-select v-model="block.group.kind" style="width: 110px" @change="onGroupKindChange">
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
        <el-form-item v-if="['pie', 'funnel'].includes(block.chart_type)" label="取前 N 项（其余合并「其他」）">
          <el-input-number v-model="block.top_n" :min="2" :max="30" controls-position="right" class="w-full" />
        </el-form-item>
        <!-- 占比快速计算：柱/线/面积/组合图可切换为占总计百分比 -->
        <el-form-item v-if="['bar', 'line', 'area', 'mixed'].includes(block.chart_type)" label="数值显示">
          <el-select v-model="block.quick_calc" class="w-full">
            <el-option label="原始值" value="" />
            <el-option label="占总计百分比" value="pct" />
          </el-select>
        </el-form-item>
        <!-- 对比：时间分组图表叠加一条虚线的上期/去年同期系列 -->
        <el-form-item
          v-if="['day', 'week', 'month'].includes(block.group.kind) && ['bar', 'line', 'area', 'mixed'].includes(block.chart_type)"
          label="对比"
        >
          <el-select v-model="block.compare" class="w-full">
            <el-option label="无" value="" />
            <el-option label="环比（上一期）" value="mom" />
            <el-option label="同比（去年同期）" value="yoy" />
          </el-select>
          <div v-if="block.compare" class="item-hint">按桶位对齐（本周一 vs 上周一…），对比系列为虚线折线</div>
        </el-form-item>
        <el-form-item label="点击图表">
          <el-select v-model="block.on_click" class="w-full" @change="onClickActionChange">
            <el-option label="下钻查看明细" value="drill" />
            <!-- 联动/跳转需要按字段分组（backend 才回传 group_field），时间分组时只提供下钻 -->
            <el-option v-if="block.group.kind === 'field'" label="联动过滤其他区块" value="link" />
            <el-option v-if="block.group.kind === 'field'" label="跳转其他报表（带分组值过滤）" value="jump" />
          </el-select>
          <div v-if="block.group.kind !== 'field'" class="item-hint">按日/周/月分组时点柱子/点即可下钻该时段明细</div>
        </el-form-item>
        <!-- 跳转目标：点分组后带着该值跳到目标报表（作为其联动过滤） -->
        <el-form-item v-if="block.on_click === 'jump'" label="目标报表">
          <el-select v-model="block.jump_report_id" class="w-full" filterable placeholder="选择要跳转的报表">
            <el-option v-for="r in reportOptions" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
          <div class="item-hint">目标报表里需有按「{{ groupFieldLabel }}」字段分组的图表，才能接住跳转的过滤值</div>
        </el-form-item>
        <!-- 层级钻取：点分组后本图换成下一层字段（如 区域 → 城市）并过滤上级值 -->
        <el-form-item
          v-if="block.group.kind === 'field' && (!block.on_click || block.on_click === 'drill') && ['bar', 'line', 'area'].includes(block.chart_type)"
          label="层级钻取"
        >
          <el-select
            :model-value="block.drill_down?.field || ''" class="w-full" clearable placeholder="不启用"
            @update:model-value="setDrillDown"
          >
            <el-option v-for="f in drillDownFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
          </el-select>
          <div v-if="block.drill_down?.field" class="item-hint">查看页点击分组，本图切换为按该字段分组并只保留上级值（面包屑可返回）</div>
        </el-form-item>

        <!-- 多系列（饼图/漏斗单系列；组合图强制多指标） -->
        <template v-if="!['pie', 'funnel'].includes(block.chart_type)">
          <el-form-item label="系列">
            <div class="row" style="align-items: center">
              <el-radio-group :model-value="seriesMode(block)" @change="(v) => setSeriesMode(block, v)">
                <el-radio-button value="single" :disabled="block.chart_type === 'mixed'">单指标</el-radio-button>
                <el-radio-button value="metrics">多指标</el-radio-button>
                <el-radio-button value="group2" :disabled="block.chart_type === 'mixed'">二级分组</el-radio-button>
              </el-radio-group>
              <el-checkbox
                v-if="seriesMode(block) !== 'single' && block.chart_type !== 'mixed'"
                v-model="block.stack" style="margin-left: 10px"
              >堆叠</el-checkbox>
            </div>
            <div v-if="block.chart_type === 'mixed'" class="item-hint">组合图：每个指标可选画成柱状（左轴）或折线（右轴）</div>
          </el-form-item>
          <template v-if="seriesMode(block) === 'metrics'">
            <div v-for="(m, mi) in block.metrics" :key="mi" class="metric-card">
              <div class="row">
                <el-select v-if="block.chart_type === 'mixed'" v-model="m.chart" style="width: 76px">
                  <el-option label="柱状" value="bar" />
                  <el-option label="折线" value="line" />
                </el-select>
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
              @click="block.metrics.push({ agg: 'count', field: null, title: '', ...(block.chart_type === 'mixed' ? { chart: 'line' } : {}) })"
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
      <el-form-item>
        <template #label>
          <span class="col-label">
            <span>展示列</span>
            <el-checkbox
              :model-value="allColsSelected" :indeterminate="someColsSelected" size="small" class="col-all"
              @change="toggleAllCols"
            >全选</el-checkbox>
            <span class="col-hint">（不选 = 默认全部字段）</span>
          </span>
        </template>
        <el-select v-model="block.columns" multiple filterable placeholder="不选 = 默认全部字段" class="w-full">
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
    </template>

    <!-- 文本 -->
    <template v-else-if="block.type === 'text'">
      <el-form-item label="内容">
        <el-input
          ref="textContentEl" v-model="block.content" type="textarea" :rows="3"
          placeholder="写报表说明/小结，下面点变量即可插入，不用记语法"
        />
      </el-form-item>
      <el-form-item label="插入变量">
        <div>
          <el-tag
            v-for="v in TEXT_VARS" :key="v.expr" size="small" type="info" effect="plain"
            class="var-tag" :title="v.expr" @click="insertTextVar(v.expr)"
          >{{ v.label }}</el-tag>
          <el-tag
            v-for="s in statBlocks" :key="s.id" size="small" type="warning" effect="plain"
            class="var-tag" :title="`{${s.id}}`" @click="insertTextVar(`{${s.id}}`)"
          >{{ s.title || s.id }}的值</el-tag>
          <div class="item-hint">点一下插入到光标处；查看/推送时会替换成真实值（橙色 = 对应统计卡的数值）</div>
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
import { computed, nextTick, ref, watch } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { listReports } from '../api'

const props = defineProps({
  block: { type: Object, required: true },      // 就地修改
  fields: { type: Array, default: () => [] },   // 数据集字段（含关联/计算字段）
  statBlocks: { type: Array, default: () => [] }, // 文本占位符引用的统计卡列表
})
const block = computed(() => props.block)

// ---------- 跳转其他报表 / 层级钻取 ----------
const reportOptions = ref([])
let reportsLoaded = false

// 选中「跳转其他报表」时懒加载报表列表
watch(() => props.block.on_click, async (v) => {
  if (v === 'jump' && !reportsLoaded) {
    reportsLoaded = true
    try { reportOptions.value = await listReports() } catch { /* 列表加载失败下拉为空 */ }
  }
}, { immediate: true })

const groupFieldLabel = computed(() =>
  props.fields.find((f) => f.field_name === props.block.group?.field)?.label || props.block.group?.field || '分组'
)

// 层级钻取字段：同数据集的其它字段（不能是分组字段本身，日期字段意义不大但允许）
const drillDownFields = computed(() =>
  props.fields.filter((f) => f.field_name !== props.block.group?.field)
)

function setDrillDown(v) {
  if (v) {
    props.block.drill_down = { field: v }
  } else {
    delete props.block.drill_down
  }
}

// 联动/跳转与层级钻取互斥（后端校验同样拦截）
function onClickActionChange(v) {
  if (v === 'link' || v === 'jump') delete props.block.drill_down
}

// ---------- 文本块：插入变量（系统变量 + 各统计卡的值；点击插到光标处，不用记 {b1} 语法） ----------
const TEXT_VARS = [
  { label: '时间范围', expr: '{range_label}' },
  { label: '开始日期', expr: '{start}' },
  { label: '结束日期', expr: '{end}' },
]
const textContentEl = ref(null)

function insertTextVar(expr) {
  const b = props.block
  const v = b.content || ''
  const el = textContentEl.value?.textarea ?? textContentEl.value?.$el?.querySelector('textarea')
  if (!el) {
    b.content = v + expr
    return
  }
  const start = el.selectionStart ?? v.length
  b.content = v.slice(0, start) + expr + v.slice(el.selectionEnd ?? start)
  nextTick(() => {
    el.focus()
    el.selectionStart = el.selectionEnd = start + expr.length
  })
}

// 明细表展示列：全选/半选/清空
const ALL_COLS = computed(() => ['id', ...props.fields.map((f) => f.field_name), 'created_at', 'updated_at'])
const allColsSelected = computed(() =>
  ALL_COLS.value.length > 0 && ALL_COLS.value.every((c) => (props.block.columns || []).includes(c)))
const someColsSelected = computed(() => (props.block.columns || []).length > 0 && !allColsSelected.value)

function toggleAllCols(v) {
  props.block.columns = v ? [...ALL_COLS.value] : []
}

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
  const b = props.block
  if (['pie', 'funnel'].includes(v)) setSeriesMode(b, 'single')
  if (v === 'mixed') {
    // 组合图强制多指标：从单指标带入第一个指标，再补一个折线指标占位
    if (seriesMode(b) !== 'metrics') setSeriesMode(b, 'metrics')
    b.metrics.forEach((m, i) => { m.chart = m.chart || (i === 0 ? 'bar' : 'line') })
    if (b.metrics.length < 2) b.metrics.push({ agg: 'count', field: null, title: '', chart: 'line' })
    b.stack = false
  }
  if (['pie', 'funnel', 'gauge'].includes(v)) b.quick_calc = ''   // 占比对饼/漏斗/仪表盘无意义
  if (v === 'gauge') {
    b.metrics = []
    b.group2 = { field: null }
    b.stack = false
    b.max = b.max || 100
    b.compare = ''
  }
}

// 分组方式切换的联动清理：联动/跳转需要按字段分组；对比（环比/同比）需要时间分组
function onGroupKindChange(v) {
  if (v !== 'field' && ['link', 'jump'].includes(props.block.on_click)) props.block.on_click = 'drill'
  if (v === 'field') props.block.compare = ''
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
/* 明细表「展示列」标签行：文本与 checkbox 水平对齐（checkbox 默认固定高度会顶起整行） */
.col-label { display: inline-flex; align-items: center; }
.col-all { margin-left: 12px; height: auto; }
.col-hint { font-size: 12px; color: #c0c4cc; font-weight: normal; }
.sub { font-size: 12px; color: #909399; }
.hint { font-size: 12px; color: #c0c4cc; margin: -6px 0 10px; }
/* form-item 内部的提示（el-form-item__content 是 flex，需独占一行并给正常间距） */
.item-hint { width: 100%; font-size: 12px; color: #c0c4cc; line-height: 1.5; margin-top: 4px; }
.sec-divider { margin: 18px 0 12px; }
.metric-card { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.var-tag { margin: 0 6px 4px 0; cursor: pointer; }
.rule-card { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; margin-bottom: 8px; background: #fafafa; }
</style>
