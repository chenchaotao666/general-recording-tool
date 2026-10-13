<template>
  <!-- 仪表盘页面（设计文档 §2.5.1）：widget 网格 + 空状态引导 -->
  <div class="dash-page">
    <div class="page-header">
      <h3>{{ name }}</h3>
      <el-button type="primary" size="small" @click="openConfig(null)">＋ 添加图表</el-button>
    </div>

    <div v-if="!widgets.length" class="empty">
      <div class="empty-cards">
        <div class="demo-card bar-demo"><i v-for="h in [60, 90, 45, 75]" :key="h" :style="{ height: `${h}%` }" /></div>
        <div class="demo-card line-demo">📈</div>
        <div class="demo-card metric-demo">¥ 6,023</div>
      </div>
      <h3>用仪表盘实时展示业务趋势</h3>
      <p class="hint">可添加柱状图、饼图、折线图等图表展示数据，关注业务动向，快速获取洞察。</p>
      <el-button type="primary" @click="openConfig(null)">添加图表</el-button>
    </div>

    <div v-else class="widgets">
      <el-card v-for="w in widgets" :key="w.id" shadow="never" class="widget">
        <template #header>
          <div class="w-head">
            <span>{{ w.title }}</span>
            <span class="w-ops">
              <el-button link size="small" @click="openConfig(w)">编辑</el-button>
              <el-button link size="small" type="danger" @click="removeWidget(w)">删除</el-button>
            </span>
          </div>
        </template>
        <div :ref="(el) => mountChart(el, w)" class="w-chart" />
      </el-card>
    </div>

    <ChartConfigDialog :visible="cfgVisible" :widget="editing" :entry-id="entryId"
                       @close="cfgVisible = false" @save="onSave" />
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import ChartConfigDialog from '../../components/smart/dashboard/ChartConfigDialog.vue'
import { renderChart } from '../../components/smart/dashboard/chartRender.js'
import {
  getTable, listTables, smartChartPreview, smartDeleteWidget,
  smartListWidgets, smartCreateWidget, smartUpdateWidget, smartGetTree, smartGetDoc,
} from '../../api/index.js'

const route = useRoute()
const entryId = Number(route.params.entryId)
const name = ref('仪表盘')
const widgets = ref([])
const dataMap = ref(new Map())
const tables = ref([])
const fieldsMap = ref(new Map())

const cfgVisible = ref(false)
const editing = ref(null)

async function load() {
  widgets.value = (await smartListWidgets(entryId)).widgets
  const doc = await smartGetDoc()
  const tree = await smartGetTree(doc.id)
  name.value = tree.entries.find(e => e.id === entryId)?.name || '仪表盘'
  const r = await listTables()
  tables.value = Array.isArray(r) ? r : (r.tables || [])
  // 每个 widget 的数据
  const next = new Map()
  for (const w of widgets.value) {
    const c = w.config || {}
    if (!c.sourceTableId || !c.dimension) continue
    if (!fieldsMap.value.has(c.sourceTableId)) {
      const meta = await getTable(c.sourceTableId)
      fieldsMap.value.set(c.sourceTableId, meta.fields)
    }
    next.set(w.id, await smartChartPreview({
      tableId: c.sourceTableId, dimension: c.dimension, subDimension: c.subDimension || undefined,
      metric: c.metric, splitMulti: c.splitMulti,
    }))
  }
  dataMap.value = next
  await nextTick()
  renderAll()
}

function mountChart(el, w) { if (el) setTimeout(() => renderOne(el, w), 0) }
function renderOne(el, w) {
  const c = w.config || {}
  renderChart(el, w.chart_type, w.sub_type, dataMap.value.get(w.id),
              tables.value, fieldsMap.value.get(c.sourceTableId) || [], c)
}
function renderAll() {
  document.querySelectorAll('.w-chart').forEach(() => {})   // ref 回调已逐个渲染
}

function openConfig(w) { editing.value = w; cfgVisible.value = true }
async function onSave(payload) {
  if (editing.value) await smartUpdateWidget(editing.value.id, payload)
  else await smartCreateWidget(entryId, payload)
  cfgVisible.value = false
  load()
}
async function removeWidget(w) {
  await ElMessageBox.confirm(`删除图表「${w.title}」？`, '删除', { type: 'warning' })
  await smartDeleteWidget(w.id)
  load()
}

onMounted(load)
</script>

<style scoped>
.dash-page { padding: 16px 24px; background: #f5f7fa; min-height: 100%; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h3 { margin: 0; }
.empty { display: flex; flex-direction: column; align-items: center; padding: 80px 0; gap: 12px; }
.empty-cards { display: flex; gap: 16px; margin-bottom: 8px; }
.demo-card { width: 140px; height: 90px; background: #fff; border-radius: 8px; box-shadow: var(--el-box-shadow-lighter); display: flex; align-items: flex-end; justify-content: center; gap: 8px; padding: 12px; }
.bar-demo i { width: 16px; background: #c3d9fb; border-radius: 3px; display: block; }
.line-demo, .metric-demo { align-items: center; justify-content: center; font-size: 28px; color: #5B8FF9; }
.metric-demo { font-weight: 700; }
.hint { color: #909399; font-size: 13px; margin: 0 0 8px; }
.widgets { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; }
.w-head { display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
.w-chart { height: 280px; }
</style>
