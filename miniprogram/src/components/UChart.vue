<template>
  <canvas
    type="2d" :id="cid"
    :style="{ width: cssWidth + 'px', height: heightPx + 'px' }"
    @touchstart="onTouch" @touchmove="onTouch" @touchend="onTouchEnd"
  />
</template>

<script setup>
// u-charts 封装：把报表的 {chart_type, labels, values, series, stack} 渲染成柱状/折线/面积/饼图
// 用 canvas 2d 并显式设置画布像素尺寸，保证各端（开发者工具/真机）渲染一致
import { getCurrentInstance, onMounted, watch } from 'vue'
import uCharts from '@qiun/ucharts'

const props = defineProps({
  type: { type: String, default: 'bar' },   // bar / line / area / pie
  labels: { type: Array, default: () => [] },
  values: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },  // [{name, values}]，多系列时优先于 values
  stack: { type: Boolean, default: false },
  heightPx: { type: Number, default: 220 },
})

let seq = 0
const cid = `uchart-${Date.now()}-${++seq}-${Math.floor(Math.random() * 1000)}`
const instance = getCurrentInstance()
let chart = null

const info = uni.getWindowInfo ? uni.getWindowInfo() : uni.getSystemInfoSync()
const pixelRatio = info.pixelRatio || 1
// 卡片内容宽度 = 屏宽 − 页面左右 padding 24rpx − 卡片左右 padding 28rpx（750rpx 设计宽度）
const cssWidth = Math.round((info.windowWidth || 375) * (1 - (2 * (24 + 28)) / 750))

function draw() {
  if (!props.labels.length) return
  uni.createSelectorQuery()
    .in(instance.proxy)
    .select(`#${cid}`)
    .fields({ node: true, size: true })
    .exec((res) => {
      const canvas = res && res[0] && res[0].node
      if (!canvas) return
      // 2d 画布坐标系 = canvas.width/height，显式设为 逻辑尺寸 × dpr，
      // CSS 尺寸保持逻辑尺寸，高分屏下清晰且不会放大
      canvas.width = cssWidth * pixelRatio
      canvas.height = props.heightPx * pixelRatio
      const ctx = canvas.getContext('2d')
      const common = {
        context: ctx,
        canvas2d: true,
        width: canvas.width,
        height: canvas.height,
        pixelRatio,
        // 注意：uCharts 顶层 color 是系列配色数组，不能传字符串
        fontSize: 11,
        animation: false,
      }
      if (props.type === 'pie') {
        chart = new uCharts({
          ...common, type: 'pie',
          series: [{ data: props.labels.map((l, i) => ({ name: String(l), value: props.values[i] || 0 })) }],
          // 不画数值标签和外部指示线，避免类目标签重叠；明细看下方数据表
          dataLabel: false,
          extra: { pie: { activeRadius: 0 } },
          legend: { show: true, position: 'bottom' },
        })
      } else {
        // 不画数值标签（会叠在一起），明细看下方数据表；
        // 类目多时按 labelCount 抽稀横轴标签
        const crowded = props.labels.length > 6
        const seriesList = (props.series && props.series.length)
          ? props.series.map((s) => ({ name: String(s.name || '值'), data: (s.values || []).map((v) => v ?? 0) }))
          : [{ name: '值', data: props.values.map((v) => v ?? 0) }]
        const multi = seriesList.length > 1
        const uType = props.type === 'line' ? 'line' : props.type === 'area' ? 'area' : 'column'
        chart = new uCharts({
          ...common,
          type: uType,
          categories: props.labels.map(String),
          series: seriesList,
          dataLabel: false,
          legend: { show: multi, position: 'bottom' },
          // Y 轴从 0 开始：否则 uCharts 会按数据最小值（如 900）做下限，柱子向下溢出横轴标签区
          yAxis: { data: [{ min: 0 }] },
          xAxis: { fontSize: 10, labelCount: crowded ? 5 : 10 },
          // uCharts 的 fixColumeData 会直接读 opts.extra.column.seriesGap，不能缺省
          extra: uType === 'column'
            // 堆叠柱状图：extra.column.type = 'stack'
            ? { column: { seriesGap: 2, categoryGap: 3, ...(props.stack && multi ? { type: 'stack' } : {}) } }
            : uType === 'area'
              ? { area: { type: 'curve', addLine: true } }
              : { line: { type: 'curve' } },
        })
      }
    })
}

onMounted(() => setTimeout(draw, 50))
watch(() => [props.labels, props.values, props.series], () => setTimeout(draw, 50), { deep: true })

// 点击/滑动柱子显示数值提示，松手重绘清除
function onTouch(e) {
  if (chart) chart.showToolTip(e)
}
function onTouchEnd() {
  draw()
}
</script>
