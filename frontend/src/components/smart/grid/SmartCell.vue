<template>
  <!-- 展示态单元格：按 field_type 分发渲染（值与显示分离，存原始值） -->
  <span class="smart-cell" :class="`cell-${field.field_type || 'text'}`">{{ display }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
})

const display = computed(() => {
  const v = props.record[props.field.field_name]
  if (v == null || v === '') return ''
  const cfg = props.field.options || {}
  const ft = props.field.field_type

  if (ft === 'singleSelect') {
    const opt = (cfg.options || []).find(o => o.id === v)
    return opt ? opt.label : String(v)
  }
  if (ft === 'multiSelect') {
    if (!Array.isArray(v)) return String(v)
    return v.map(id => (cfg.options || []).find(o => o.id === id)?.label ?? id).join('、')
  }
  if (ft === 'checkbox') return v ? '✓' : ''
  if (ft === 'url') return (v && typeof v === 'object') ? (v.text || v.url) : String(v)
  if (ft === 'member') return Array.isArray(v) ? `${v.length} 人` : String(v)
  if (ft === 'percent') return `${v}%`
  if (ft === 'currency') {
    const n = Number(v)
    const num = cfg.precision != null && cfg.precision !== 'default' ? n.toFixed(cfg.precision) : String(v)
    const sep = cfg.thousandSeparator !== false ? num.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : num
    return `${cfg.currencySymbol || '￥'}${sep}`
  }
  if ((ft === 'number') && cfg.thousandSeparator) {
    return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  }
  if (ft === 'date') return String(v).slice(0, cfg.includeTime ? 16 : 10)
  return String(v)
})
</script>

<style scoped>
.smart-cell { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.cell-checkbox { color: var(--el-color-success); font-weight: 700; text-align: center; }
.cell-currency, .cell-number, .cell-percent { text-align: right; }
</style>
