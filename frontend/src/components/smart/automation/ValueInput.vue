<template>
  <!-- 动作赋值：静态值（按目标字段类型给编辑器）或变量胶囊（{x} 选择「第 N 步的…」/ 自然时间） -->
  <div class="vi">
    <DateValueInput v-if="ft === 'date'" :model-value="modelValue" :field="field" :steps="steps" @update:model-value="v => emit('update:modelValue', v)" />
    <span v-else-if="isVar" class="vi-chip">{{ modelValue.label || '变量' }}<span class="vi-x" @click="emit('update:modelValue', undefined)">✕</span></span>
    <template v-else-if="field">
      <el-popover v-if="isSelect" v-model:visible="optionsOpen" trigger="click" placement="top-start" :width="320"
                  :hide-after="0" :show-arrow="false" :teleported="false" :popper-options="{ strategy: 'fixed' }" popper-class="vi-option-pop">
        <template #reference>
          <button type="button" class="vi-enum-trigger">
            <span v-if="!chosenOptions.length" class="vi-placeholder">请选择</span>
            <span v-for="o in chosenOptions" :key="o.id" class="vi-option-tag" :style="tagStyle(o)">{{ o.label }}</span>
            <StIcon name="chevron-down" :size="14" class="vi-caret" />
          </button>
        </template>
        <div class="vi-option-search"><el-input v-model="search" placeholder="搜索" clearable /></div>
        <div class="vi-option-list">
          <button v-for="o in filteredOptions" :key="o.id" type="button" class="vi-option-row" @click="pickOption(o)">
            <span class="vi-option-tag" :style="tagStyle(o)">{{ o.label }}</span>
            <span v-if="chosenOptions.some(c => c.id === o.id)" class="vi-check">✓</span>
          </button>
          <div v-if="!filteredOptions.length" class="vi-no-options">暂无匹配选项</div>
        </div>
        <button v-if="chosenOptions.length" type="button" class="vi-clear-value" @click="setStatic(ft === 'multiSelect' ? [] : null)">清空值</button>
        <VarMenu :steps="steps" value-mode inline @pick="pickVar" />
      </el-popover>
      <el-select v-else-if="ft === 'member'" :model-value="staticVal" multiple class="vi-in" :teleported="false"
                 placeholder="选择成员" @update:model-value="setStatic">
        <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
      </el-select>
      <el-switch v-else-if="ft === 'checkbox'" :model-value="!!staticVal" @update:model-value="setStatic" />
      <el-input-number v-else-if="isNumber" :model-value="staticVal" class="vi-in" controls-position="right"
                       @update:model-value="setStatic" />
      <el-input v-else :model-value="staticVal" class="vi-in" placeholder="请输入" @update:model-value="setStatic" />
    </template>
    <span v-if="!field" class="vi-placeholder vi-in">请先选择字段</span>
    <el-popover v-if="field && ft !== 'date' && (!isSelect || isVar)" v-model:visible="varsOpen" trigger="click"
                placement="bottom-end" :width="232" :hide-after="0" :show-arrow="false" :teleported="false"
                :popper-options="{ strategy: 'fixed' }" popper-class="vi-vars-pop">
      <template #reference><button type="button" class="vi-var" aria-label="插入变量" data-smart-tip="插入变量">{x}</button></template>
      <VarMenu :steps="steps" value-mode inline @pick="pickVar" />
    </el-popover>
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import VarMenu from './VarMenu.vue'
import DateValueInput from './DateValueInput.vue'
import StIcon from '../icons/StIcon.vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  modelValue: { type: [Object, String, Number, Boolean, Array], default: undefined },  // {type:'static',value}|{type:'var',var,label}
  field: { type: Object, default: null },
  steps: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])
const members = inject('smartMembers', { value: [] })

const ft = computed(() => props.field?.field_type)
const isVar = computed(() => props.modelValue?.type === 'var')
const isSelect = computed(() => ['singleSelect', 'multiSelect'].includes(ft.value))
const isNumber = computed(() => ['number', 'percent', 'currency', 'progress'].includes(ft.value))
const staticVal = computed(() => (props.modelValue?.type === 'static' ? props.modelValue.value : undefined))
const varsOpen = ref(false)
const optionsOpen = ref(false)
const search = ref('')
const options = computed(() => props.field?.options?.options || [])
const chosenOptions = computed(() => options.value.filter(o => ft.value === 'multiSelect'
  ? (Array.isArray(staticVal.value) && staticVal.value.includes(o.id)) : staticVal.value === o.id))
const filteredOptions = computed(() => options.value.filter(o => o.label.toLowerCase().includes(search.value.trim().toLowerCase())))
const tagStyle = o => ({ background: optionColor(o.color).value, color: optionColor(o.color).text })
watch(() => props.field?.field_name, () => { optionsOpen.value = false; search.value = ''; varsOpen.value = false })
function pickOption(o) {
  if (ft.value === 'multiSelect') {
    const values = Array.isArray(staticVal.value) ? staticVal.value : []
    setStatic(values.includes(o.id) ? values.filter(id => id !== o.id) : [...values, o.id])
  } else { setStatic(o.id); optionsOpen.value = false }
}

function setStatic(v) { emit('update:modelValue', { type: 'static', value: v }) }
function pickVar(v, label) {
  emit('update:modelValue', { type: 'var', var: v, label })
  varsOpen.value = false
  optionsOpen.value = false
}
</script>

<style scoped>
.vi { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.vi-in { flex: 1; min-width: 0; width: 100%; }
.vi-chip { flex: 1; display: inline-flex; align-items: center; justify-content: space-between; gap: 6px; background: #F0F1F3; border-radius: 4px; padding: 4px 10px; font-size: var(--st-font-size); }
.vi-x { color: var(--st-text-3); cursor: pointer; }
.vi-var { flex: none; font-size: var(--st-font-size); color: var(--st-text-2); background: #fff; cursor: pointer; border: 1px solid var(--st-border); border-radius: 4px; padding: 3px 6px; font-family: monospace; }
.vi-var:hover { color: var(--st-primary); border-color: var(--st-primary); }
.vi-enum-trigger { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; width: 100%; min-height: 36px; padding: 5px 9px; border: 1px solid var(--st-border); border-radius: 6px; background: #fff; cursor: pointer; text-align: left; }
.vi-placeholder { color: var(--st-text-4); font-size: var(--st-font-size); }
.vi-caret { margin-left: auto; color: var(--st-text-3); }
.vi-option-search { padding: 8px; border-bottom: 1px solid var(--st-border); }
.vi-option-list { max-height: 220px; overflow: auto; padding: 6px; }
.vi-option-row { display: flex; align-items: center; gap: 8px; width: 100%; border: 0; background: #fff; padding: 0 12px; text-align: left; cursor: pointer; border-radius: 4px;  height: var(--st-list-item-height); box-sizing: border-box; }
.vi-option-row:hover { background: var(--st-bg-hover); }
.vi-option-tag { display: inline-block; border-radius: 4px; padding: 2px 7px; font-size: var(--st-font-size); line-height: 22px; overflow-wrap: anywhere; }
.vi-check { margin-left: auto; color: var(--st-primary); }
.vi-clear-value { width: 100%; border: 0; background: none; padding: 8px 18px; text-align: left; color: var(--st-text-3); cursor: pointer; }
.vi-no-options { padding: 12px; color: var(--st-text-3); text-align: center; font-size: var(--st-font-size); }
</style>

<style>
.vi-option-pop.el-popover { padding: 0; border-radius: 6px; }
.vi-vars-pop.el-popover { padding: 0; border-radius: 6px; }
.vi-vars-pop .vm.vm-inline { border-top: 0; border-radius: 6px; }
</style>
