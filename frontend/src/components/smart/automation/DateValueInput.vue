<template>
  <el-popover v-model:visible="open" trigger="click" placement="bottom-start" :width="320"
              :hide-after="0" :show-arrow="false" :teleported="false" :popper-options="{ strategy: 'fixed' }"
              popper-class="dvi-pop" @hide="specific = false">
    <template #reference>
      <button type="button" class="dvi-trigger">
        <span :class="{ placeholder: !label }">{{ label || '请选择' }}</span>
        <StIcon :name="open ? 'chevron-up' : 'chevron-down'" :size="14" />
      </button>
    </template>
    <div class="dvi-days">
      <button v-for="d in days" :key="d.key" type="button" class="dvi-item" @click="pick({ type: 'var', var: { kind: 'time', key: d.key }, label: d.label })">{{ d.label }}</button>
    </div>
    <div class="dvi-specific">
      <button type="button" class="dvi-item" @click="showSpecific">具体日期</button>
      <div v-if="specific" class="dvi-calendar">
        <el-date-picker ref="picker" :model-value="modelValue?.type === 'static' ? modelValue.value : null"
                        :type="field.options?.includeTime ? 'datetime' : 'date'"
                        :value-format="field.options?.includeTime ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD'"
                        :teleported="false" placeholder="选择具体日期" @update:model-value="v => pick({ type: 'static', value: v })" />
      </div>
    </div>
    <VarMenu v-if="open && steps.length" :steps="dateSteps" value-mode inline hide-time @pick="(v, text) => pick({ type: 'var', var: v, label: text })" />
    <button v-if="label" type="button" class="dvi-item dvi-clear" @click="pick(undefined)">清空值</button>
  </el-popover>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
import VarMenu from './VarMenu.vue'
const props = defineProps({ modelValue: { default: undefined }, field: { type: Object, required: true }, steps: { type: Array, default: () => [] } })
const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const specific = ref(false)
const picker = ref(null)
const dateSteps = computed(() => props.steps.map(step => ({
  ...step,
  vars: (step.vars || []).filter(v => ['date', 'createdTime', 'lastModifiedTime'].includes(v.icon)),
})))
const days = [{ key: 'today', label: '今天' }, { key: 'tomorrow', label: '明天' }, { key: 'yesterday', label: '昨天' }]
const label = computed(() => props.modelValue?.type === 'var'
  ? (props.modelValue.label || days.find(d => d.key === props.modelValue.var?.key)?.label || '日期变量')
  : props.modelValue?.value || '')
function pick(value) { emit('update:modelValue', value); open.value = false; specific.value = false }
async function showSpecific() {
  specific.value = true
  await nextTick()
  picker.value?.handleOpen?.()
}
</script>

<style scoped>
.dvi-trigger { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; min-width: 0; min-height: 36px; padding: 6px 12px; border: 1px solid var(--st-border); border-radius: 6px; background: #fff; font: inherit; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; text-align: left; }
.dvi-trigger > span { min-width: 0; overflow-wrap: anywhere; }
.placeholder { color: var(--st-text-4); }
.dvi-days { padding: 6px; }
.dvi-item { display: block; width: 100%; padding: 0 16px; text-align: left; border: 0; border-radius: 4px; background: #fff; color: var(--st-text-2); font: inherit; font-size: var(--st-font-size); cursor: pointer;  height: var(--st-list-item-height); box-sizing: border-box; }
.dvi-item:hover { background: var(--st-bg-hover); }
.dvi-specific { padding: 6px; border-top: 1px solid var(--st-border); }
.dvi-calendar { padding: 4px 10px 8px; }
.dvi-calendar :deep(.el-date-editor) { width: 100%; }
.dvi-clear { color: var(--st-text-3); border-top: 1px solid var(--st-border); border-radius: 0; }
</style>
<style>
.dvi-pop.el-popover { padding: 0; border-radius: 6px; }
</style>
