<template>
  <span class="progress-cell" @dblclick="enterEdit">
    <span class="progress-track">
      <span class="progress-fill" :style="fillStyle" />
      <input v-if="interactive" class="progress-slider" type="range" :value="sliderValue" :min="min" :max="max" :step="step"
             aria-label="调整进度" @input="draft = Number($event.target.value)" @change="emit('commit', Number($event.target.value))"
             @click.stop @mousedown.stop @keydown.enter.prevent="emit('enter-edit')" @keydown.esc="emit('cancel')" />
    </span>
    <span v-if="config.showNumber !== false" class="progress-number">{{ label }}</span>
  </span>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { progressColor } from '../../../smart/registry/fieldRegistry.js'
const props = defineProps({ value: [Number, String], config: { type: Object, default: () => ({}) }, interactive: Boolean })
const emit = defineEmits(['commit', 'enter-edit', 'cancel'])
const min = computed(() => Number(props.config.range?.min ?? 0))
const max = computed(() => Math.max(min.value + 1, Number(props.config.range?.max ?? 100)))
const step = computed(() => Number.isInteger(props.config.precision) ? 10 ** -props.config.precision : 1)
const draft = ref(props.value)
watch(() => props.value, value => { draft.value = value })
// 原生 range 收到空值会默认停在中点；仅给滑块提供起点，不把空记录写成 0。
const sliderValue = computed(() => draft.value == null || draft.value === '' ? min.value : Number(draft.value))
const ratio = computed(() => Math.min(1, Math.max(0, (sliderValue.value - min.value) / (max.value - min.value))))
const fillStyle = computed(() => ({ width: `${ratio.value * 100}%`, background: progressColor(props.config.color, ratio.value) }))
const label = computed(() => {
  if (draft.value == null || draft.value === '') return ''
  const percent = props.config.numberFormat === 'percent'
  const value = percent ? (Number(draft.value) - min.value) / (max.value - min.value) * 100 : Number(draft.value)
  const precision = props.config.precision
  const text = precision == null || precision === 'default' ? String(+value.toFixed(4)) : value.toFixed(precision)
  return text + (percent ? '%' : '')
})
function enterEdit(event) {
  if (props.interactive) { event.stopPropagation(); emit('enter-edit') }
}
</script>

<style scoped>
.progress-cell { display: flex; align-items: center; gap: 16px; width: 100%; min-width: 0; min-height: 22px; height: 100%; }
.progress-track { flex: 1; min-width: 20px; height: 12px; position: relative; background: #f1f2f3; border-radius: 2px; }
.progress-fill { display: block; height: 100%; border-radius: 2px 0 0 2px; }
.progress-number { flex: none; min-width: 34px; text-align: right; font-size: 13px; color: var(--st-text-1); font-variant-numeric: tabular-nums; }
.progress-slider { appearance: none; -webkit-appearance: none; position: absolute; inset: -5px 0; width: 100%; height: 22px; margin: 0; background: transparent; outline: none; cursor: pointer; }
.progress-slider::-webkit-slider-runnable-track { height: 12px; background: transparent; }
.progress-slider::-webkit-slider-thumb { appearance: none; -webkit-appearance: none; width: 8px; height: 18px; margin-top: -3px; border: 1px solid #d9dde2; border-radius: 3px; background: white; cursor: ew-resize; }
.progress-slider::-moz-range-track { height: 12px; background: transparent; }
.progress-slider::-moz-range-thumb { width: 6px; height: 16px; border: 1px solid #d9dde2; border-radius: 3px; background: white; cursor: ew-resize; }
.progress-slider:focus-visible { outline: 1px solid var(--st-primary); outline-offset: 3px; border-radius: 2px; }
</style>
