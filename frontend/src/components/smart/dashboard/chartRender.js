// 图表渲染：聚合结果 → ECharts option（柱状/折线/饼/条形/指标卡/表格）
import * as echarts from 'echarts'

const PALETTE = ['#5B8FF9', '#61DDAA', '#F6BD16', '#7262FD', '#78D3F8', '#9661BC', '#F6903D', '#008685']

export function renderChart(el, chartType, subType, data, tables, fields, cfg) {
  if (!el || !data) return
  let inst = echarts.getInstanceByDom(el)
  if (!inst) inst = echarts.init(el)
  const cats = data.categories || []
  const keys = cats.map(c => c.key)
  const dimLabel = fields.find(f => f.field_name === cfg?.dimension)?.label || ''
  const metricLabel = cfg?.metric?.agg === 'count' ? '记录数'
    : `${{ sum: '求和', avg: '平均', max: '最大', min: '最小' }[cfg?.metric?.agg] || ''}`

  if (chartType === 'metric') {
    const total = cats.reduce((s, c) => s + (c.value || 0), 0)
    inst.setOption({
      title: { text: String(total), subtext: metricLabel, left: 'center', top: 'center',
               textStyle: { fontSize: 40 }, subtextStyle: { fontSize: 14 } },
      series: [],
    }, true)
    return
  }

  if (chartType === 'table') {
    inst.clear()
    return   // 表格 widget 由页面用 el-table 渲染
  }

  const hasSub = cats.some(c => c.children?.length)
  let series
  if (hasSub) {
    const subKeys = [...new Set(cats.flatMap(c => c.children.map(x => x.key)))]
    series = subKeys.map((sk, i) => ({
      name: sk, type: chartType === 'line' ? 'line' : 'bar',
      stack: subType === 'stacked' ? 'total' : undefined,
      data: cats.map(c => c.children.find(x => x.key === sk)?.value ?? 0),
      itemStyle: { color: PALETTE[i % PALETTE.length] },
    }))
  } else if (chartType === 'pie') {
    series = [{ type: 'pie', radius: ['40%', '70%'], data: cats.map((c, i) => ({ name: c.key, value: c.value, itemStyle: { color: PALETTE[i % PALETTE.length] } })) }]
  } else {
    series = [{
      name: metricLabel, type: chartType === 'line' ? 'line' : 'bar',
      data: cats.map((c, i) => ({ value: c.value, itemStyle: { color: PALETTE[i % PALETTE.length] } })),
      label: { show: true, position: 'top' },
    }]
  }

  const horizontal = chartType === 'barH'
  inst.setOption({
    color: PALETTE,
    tooltip: { trigger: chartType === 'pie' ? 'item' : 'axis' },
    legend: hasSub ? { bottom: 0 } : undefined,
    grid: chartType === 'pie' ? undefined : { left: 40, right: 16, top: 24, bottom: hasSub ? 40 : 24 },
    xAxis: chartType === 'pie' ? undefined : {
      type: horizontal ? 'value' : 'category', data: horizontal ? undefined : keys,
      axisLabel: { rotate: keys.some(k => k.length > 6) ? 30 : 0 },
    },
    yAxis: chartType === 'pie' ? undefined : { type: horizontal ? 'category' : 'value', data: horizontal ? keys : undefined },
    series,
  }, true)
}
