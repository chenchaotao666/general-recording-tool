<template>
  <canvas :canvas-id="cid" :id="cid" :style="{ width: '100%', height: heightPx + 'px' }" />
</template>

<script setup>
// u-charts 封装：把报表的 {chart_type, labels, values} 渲染成柱状/折线/饼图
import { getCurrentInstance, onMounted, watch } from 'vue'
import uCharts from '@qiun/ucharts'

const props = defineProps({
  type: { type: String, default: 'bar' },   // bar / line / pie
  labels: { type: Array, default: () => [] },
  values: { type: Array, default: () => [] },
  heightPx: { type: Number, default: 220 },
})

let seq = 0
const cid = `uchart-${Date.now()}-${++seq}-${Math.floor(Math.random() * 1000)}`
const instance = getCurrentInstance()
let chart = null

function draw() {
  if (!props.labels.length) return
  const info = uni.getWindowInfo ? uni.getWindowInfo() : uni.getSystemInfoSync()
  const pixelRatio = info.pixelRatio || 1
  const width = (info.windowWidth || 375) - 88   // 页面 padding + 卡片 padding 估算
  const height = props.heightPx
  const ctx = uni.createCanvasContext(cid, instance.proxy)
  const common = {
    context: ctx, width: width * pixelRatio, height: height * pixelRatio, pixelRatio,
    fontSize: 11, color: '#303133', animation: false,
  }
  if (props.type === 'pie') {
    chart = new uCharts({
      ...common, type: 'pie',
      series: [{ data: props.labels.map((l, i) => ({ name: String(l), value: props.values[i] || 0 })) }],
      extra: { pie: { activeRadius: 0, labelWidth: 12 } },
      legend: { show: true, position: 'bottom' },
    })
  } else {
    chart = new uCharts({
      ...common,
      type: props.type === 'line' ? 'line' : 'column',
      categories: props.labels.map(String),
      series: [{ name: '值', data: props.values.map((v) => v ?? 0) }],
      legend: { show: false },
      xAxis: { scrollShow: props.labels.length > 8, itemCount: 6 },
      extra: props.type === 'line' ? { line: { type: 'curve', width: 2 } } : { column: { width: 12 } },
    })
  }
}

onMounted(() => setTimeout(draw, 50))
watch(() => [props.labels, props.values], () => setTimeout(draw, 50), { deep: true })
</script>
