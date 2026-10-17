<template>
  <!-- 动作赋值：静态值（按目标字段类型给编辑器）或变量胶囊（{x} 选择「第 N 步的…」/ 自然时间） -->
  <div class="vi">
    <span v-if="isVar" class="vi-chip">{{ modelValue.label || '变量' }}<span class="vi-x" @click="emit('update:modelValue', undefined)">✕</span></span>
    <template v-else-if="field">
      <el-select v-if="isSelect" :model-value="staticVal" :multiple="ft === 'multiSelect'" class="vi-in" :teleported="false"
                 placeholder="请选择" clearable @update:model-value="setStatic">
        <el-option v-for="o in field.options?.options || []" :key="o.id" :value="o.id" :label="o.label" />
      </el-select>
      <el-select v-else-if="ft === 'member'" :model-value="staticVal" multiple class="vi-in" :teleported="false"
                 placeholder="选择成员" @update:model-value="setStatic">
        <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
      </el-select>
      <el-switch v-else-if="ft === 'checkbox'" :model-value="!!staticVal" @update:model-value="setStatic" />
      <el-input-number v-else-if="isNumber" :model-value="staticVal" class="vi-in" controls-position="right"
                       @update:model-value="setStatic" />
      <el-date-picker v-else-if="ft === 'date'" :model-value="staticVal" type="date" value-format="YYYY-MM-DD"
                      :teleported="false" class="vi-in" @update:model-value="setStatic" />
      <el-input v-else :model-value="staticVal" class="vi-in" placeholder="请输入" @update:model-value="setStatic" />
    </template>
    <span class="vi-var" title="插入变量" @click="openVars">{x}</span>
    <teleport to="body">
      <div v-if="menu.visible" class="vi-mask" @mousedown="menu.visible = false" />
      <VarMenu v-if="menu.visible" :x="menu.x" :y="menu.y" :steps="steps" value-mode @pick="pickVar" />
    </teleport>
  </div>
</template>

<script setup>
import { computed, inject, reactive } from 'vue'
import VarMenu from './VarMenu.vue'

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
const menu = reactive({ visible: false, x: 0, y: 0 })

function setStatic(v) { emit('update:modelValue', { type: 'static', value: v }) }
function openVars(e) {
  const r = e.currentTarget.getBoundingClientRect()
  Object.assign(menu, { visible: true, x: r.left - 180, y: r.bottom + 6 })
}
function pickVar(v, label) {
  emit('update:modelValue', { type: 'var', var: v, label })
  menu.visible = false
}
</script>

<style scoped>
.vi { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.vi-in { flex: 1; min-width: 0; width: 100%; }
.vi-chip { flex: 1; display: inline-flex; align-items: center; justify-content: space-between; gap: 6px; background: #F0F1F3; border-radius: 4px; padding: 4px 10px; font-size: 13px; }
.vi-x { color: var(--st-text-3); cursor: pointer; }
.vi-var { flex: none; font-size: 13px; color: var(--st-text-2); cursor: pointer; border: 1px solid var(--st-border); border-radius: 4px; padding: 3px 6px; font-family: monospace; }
.vi-var:hover { color: var(--st-primary); border-color: var(--st-primary); }
.vi-mask { position: fixed; inset: 0; z-index: 3990; }
</style>
