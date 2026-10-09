<template>
  <div class="hc report-card" @click="go">
    <div v-if="error" class="hc-invalid">{{ error }}</div>
    <div v-else-if="!block" class="hc-loading" v-loading="true" />
    <template v-else>
      <div class="rc-title">
        <el-icon><DataAnalysis /></el-icon>
        <span class="rc-name">{{ reportName }}</span>
        <!-- 时间过滤（同报表查看页的口径） -->
        <el-select
          v-model="rangeMode" size="small" class="rc-range"
          @click.stop @change="reload"
        >
          <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
        </el-select>
      </div>
      <!-- 复用报表区块渲染层（fill 填满卡片） -->
      <div class="rc-body" @click.stop>
        <ReportBlock :block="block" fill />
      </div>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { DataAnalysis } from '@element-plus/icons-vue'
import { getReport, runReport } from '../../api'
import ReportBlock from '../../components/ReportBlock.vue'
import { useAutoRefresh } from '../useAutoRefresh'

// 与报表查看页一致的时间口径（自定义范围在卡片上放不下，去完整页操作）
const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'],
]

const props = defineProps({
  config: { type: Object, default: () => ({}) },   // {report_id, block_id?, refresh?}
})
const router = useRouter()
const block = ref(null)
const reportName = ref('')
const error = ref('')
const rangeMode = ref('this_week')

async function reload() {
  try {
    const [tpl, result] = await Promise.all([
      getReport(props.config.report_id),
      runReport(props.config.report_id, { mode: rangeMode.value }),
    ])
    reportName.value = tpl.name || '报表'
    const blocks = result.blocks || []
    // 指定的区块 → 第一个统计卡/图表/透视表 → 第一个区块
    block.value = blocks.find((b) => b.id === props.config.block_id)
      || blocks.find((b) => ['stat', 'chart', 'pivot'].includes(b.type))
      || blocks[0] || null
    if (!block.value) error.value = '该报表还没有区块'
  } catch (e) {
    error.value = e.message?.includes('404') ? '报表已删除或无权访问' : '报表加载失败'
  }
}
onMounted(async () => {
  // 初始口径跟随报表模板自己的设置
  try {
    const tpl = await getReport(props.config.report_id)
    if (tpl.range?.mode && RANGE_MODES.some(([v]) => v === tpl.range.mode)) {
      rangeMode.value = tpl.range.mode
    }
  } catch { /* 用默认本周 */ }
  await reload()
})
useAutoRefresh(() => props.config, reload)

function go() {
  if (!error.value) router.push(`/reports/${props.config.report_id}/view`)
}
</script>

<style scoped>
.report-card { display: flex; flex-direction: column; }
.rc-title {
  display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600;
  color: #303133; padding-bottom: 6px; flex-shrink: 0;
}
.rc-title .el-icon { color: #9b59b6; }   /* 报表=紫（与蓝表/青菜单分色） */
.rc-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rc-range { width: 88px; flex-shrink: 0; }
.rc-range :deep(.el-select__wrapper) { min-height: 24px; font-size: 12px; }
.rc-body { flex: 1; min-height: 90px; overflow: hidden; cursor: default; }
.rc-body :deep(.rblock) { font-size: 12px; }
</style>
