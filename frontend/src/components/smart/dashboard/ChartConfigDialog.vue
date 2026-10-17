<template>
  <!-- 图表配置弹窗（设计文档 §2.5.1）：左配置右预览 -->
  <el-dialog :model-value="visible" title="图表" width="860px" @update:model-value="$emit('close')"
             destroy-on-close @open="onOpen">
    <div class="chart-cfg">
      <div class="cfg-left">
        <div class="type-grid">
          <div v-for="t in CHART_TYPES" :key="t.key" class="type-item"
               :class="{ active: form.chart_type === t.key }" @click="form.chart_type = t.key">
            <div class="t-icon">{{ t.icon }}</div>
            <div class="t-name">{{ t.label }}</div>
          </div>
        </div>
        <template v-if="form.chart_type === 'bar'">
          <el-radio-group v-model="form.sub_type" size="small">
            <el-radio-button value="">柱状图</el-radio-button>
            <el-radio-button value="stacked">堆积柱状图</el-radio-button>
          </el-radio-group>
        </template>
        <el-select v-model="form.config.sourceTableId" placeholder="数据源（智能表）" filterable
                   @change="onSourceChange">
          <el-option v-for="t in tables" :key="t.id" :value="t.id" :label="t.label" />
        </el-select>
        <el-select v-model="form.config.dimension" placeholder="横轴（类别字段）">
          <el-option v-for="f in srcFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-checkbox v-model="form.config.splitMulti" size="small">多选项拆分统计</el-checkbox>
        <el-select v-model="form.config.subDimension" placeholder="二级类别字段（可选）" clearable>
          <el-option v-for="f in srcFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <div class="metric-row">
          <el-select v-model="form.config.metric.agg" style="width: 110px">
            <el-option value="count" label="记录行数" />
            <el-option value="sum" label="求和" /><el-option value="avg" label="平均值" />
            <el-option value="max" label="最大值" /><el-option value="min" label="最小值" />
          </el-select>
          <el-select v-if="form.config.metric.agg !== 'count'" v-model="form.config.metric.field" placeholder="指标字段">
            <el-option v-for="f in numFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
          </el-select>
        </div>
      </div>
      <div class="cfg-right">
        <div ref="chartRef" class="preview" />
      </div>
    </div>
    <template #footer>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" :disabled="!form.config.sourceTableId || !form.config.dimension" @click="save">
        {{ widget ? '保存' : '添加' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { nextTick, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { getTable, listTables, smartChartPreview } from '../../../api/index.js'
import { renderChart } from './chartRender.js'

// preset：新建时的预填（表头「数据可视化 → 添加更多图表」带入数据源表与类别字段）
const props = defineProps({ visible: Boolean, widget: Object, entryId: Number, preset: Object })
const emit = defineEmits(['close', 'save'])

const CHART_TYPES = [
  { key: 'bar', label: '柱状图', icon: '📊' }, { key: 'line', label: '折线图', icon: '📈' },
  { key: 'pie', label: '饼图', icon: '🥧' }, { key: 'barH', label: '条形图', icon: '📉' },
  { key: 'metric', label: '指标卡', icon: '🔢' }, { key: 'table', label: '表格', icon: '⊞' },
]

const tables = ref([])
const srcFields = ref([])
const chartRef = ref(null)
const previewData = ref(null)

const form = reactive({
  chart_type: 'bar', sub_type: '',
  config: { sourceTableId: null, dimension: null, subDimension: null, splitMulti: true, metric: { agg: 'count', field: null } },
})

const numFields = ref([])

async function onOpen() {
  if (!tables.value.length) {
    const r = await listTables()
    tables.value = Array.isArray(r) ? r : (r.tables || [])
  }
  if (props.widget) {
    form.chart_type = props.widget.chart_type
    form.sub_type = props.widget.sub_type || ''
    form.config = JSON.parse(JSON.stringify(props.widget.config || form.config))
    if (form.config.sourceTableId) await onSourceChange(form.config.sourceTableId, true)
  } else if (props.preset?.config?.sourceTableId) {
    form.chart_type = props.preset.chart_type || 'bar'
    form.sub_type = ''
    form.config = { ...JSON.parse(JSON.stringify(form.config)), ...props.preset.config,
                    metric: props.preset.config.metric || { agg: 'count', field: null } }
    await onSourceChange(form.config.sourceTableId, true)
  }
}

async function onSourceChange(tid, keep) {
  const meta = await getTable(tid)
  srcFields.value = meta.fields
  numFields.value = meta.fields.filter(f => ['decimal', 'int'].includes(f.data_type))
  if (!keep) {
    form.config.dimension = meta.fields[0]?.field_name
    form.config.subDimension = null
    form.config.metric = { agg: 'count', field: null }
  }
}

// 配置变更 → 防抖预览
let timer = null
watch(() => [form.chart_type, form.sub_type, JSON.stringify(form.config)], () => {
  clearTimeout(timer)
  timer = setTimeout(loadPreview, 400)
})

async function loadPreview() {
  const c = form.config
  if (!c.sourceTableId || !c.dimension) return
  previewData.value = await smartChartPreview({
    tableId: c.sourceTableId, dimension: c.dimension, subDimension: c.subDimension || undefined,
    metric: c.metric, splitMulti: c.splitMulti,
  })
  await nextTick()
  renderChart(chartRef.value, form.chart_type, form.sub_type, previewData.value, tables.value, srcFields.value, c)
}

function save() {
  emit('save', { title: props.widget?.title || props.preset?.title || '图表', chart_type: form.chart_type, sub_type: form.sub_type, config: form.config })
}
</script>

<style scoped>
.chart-cfg { display: flex; gap: 16px; min-height: 380px; }
.cfg-left { width: 300px; display: flex; flex-direction: column; gap: 10px; }
.type-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.type-item { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 8px 4px; text-align: center; cursor: pointer; }
.type-item.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.t-icon { font-size: 20px; }
.t-name { font-size: 12px; margin-top: 2px; }
.metric-row { display: flex; gap: 8px; }
.cfg-right { flex: 1; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 8px; }
.preview { width: 100%; height: 360px; }
</style>
