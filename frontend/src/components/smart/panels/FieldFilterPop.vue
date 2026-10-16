<template>
  <!-- 单字段筛选浮层（对齐参照 筛选-固定到工具栏.png / 表头-筛选.png）：
       运算符 + （枚举/人员：搜索 + 已选择 N 项/清空 + 勾选列表；其余：ConditionValue）。
       即时生效：每次变更 emit 完整条件（值空时 emit null = 移除该字段条件）。
       pin 胶囊与列头「筛选」共用；调用方负责定位容器（el-popover 或 fixed 浮层） -->
  <div class="ffp" @click.stop @mousedown.stop>
    <div class="ffp-head">
      <b>筛选</b>
      <span class="ffp-scope">{{ scopeText }}</span>
    </div>
    <el-select :teleported="false" v-model="op" size="small" class="ffp-op" @change="onOpChange">
      <el-option v-for="o in ops" :key="o" :value="o" :label="OP_LABELS[o]" />
    </el-select>

    <template v-if="needsValue">
      <!-- 枚举/人员：勾选清单 -->
      <template v-if="isEnum || isMember">
        <el-input v-model="kw" size="small" :placeholder="isMember ? '搜索成员' : '搜索'" clearable class="ffp-search" />
        <div class="ffp-count">
          <span>已选择 {{ selected.length }} {{ isMember ? '人' : '项' }}</span>
          <span class="ffp-clear" :class="{ dim: !selected.length }" @click="setSelected([])">清空</span>
        </div>
        <div class="ffp-list">
          <label v-for="o in filteredOptions" :key="o.id" class="ffp-item">
            <el-checkbox :model-value="selected.includes(o.id)" size="small" @change="toggle(o.id)" />
            <span v-if="isEnum" class="ffp-tag"
                  :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
            <span v-else class="ffp-name">{{ o.label }}</span>
          </label>
          <div v-if="!filteredOptions.length" class="ffp-empty">无匹配{{ isMember ? '成员' : '选项' }}</div>
        </div>
      </template>
      <!-- 其他类型：通用值编辑器 -->
      <ConditionValue v-else :field="field" :operator="op" :value="value" @update="onValue" />
    </template>

    <div v-if="hasCondition" class="ffp-foot">
      <span class="ffp-del" @click="remove">删除条件</span>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import ConditionValue from './ConditionValue.vue'
import { filterOpsOf, OP_LABELS, NO_VALUE_OPS, optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  field: { type: Object, required: true },
  condition: { type: Object, default: null },   // 该字段的现有条件（无则 null）
  scopeText: { type: String, default: '' },
})
const emit = defineEmits(['change'])
const members = inject('smartMembers', { value: [] })

const ops = computed(() => filterOpsOf(props.field))
const isEnum = computed(() => ['singleSelect', 'multiSelect'].includes(props.field.field_type))
const isMember = computed(() => ['member', 'createdBy', 'lastModifiedBy'].includes(props.field.field_type))

const op = ref('contains')
const value = ref(undefined)
const selected = ref([])   // 枚举/人员勾选集
const kw = ref('')

watch(() => [props.field, props.condition], () => {
  kw.value = ''
  op.value = props.condition?.operator || ops.value[0] || 'contains'
  const v = props.condition?.value
  if (isEnum.value || isMember.value) {
    selected.value = Array.isArray(v) ? [...v] : (v != null ? [v] : [])
  } else {
    value.value = v
  }
}, { immediate: true, deep: true })

const needsValue = computed(() => !NO_VALUE_OPS.includes(op.value))
const hasCondition = computed(() => !!props.condition)

const listOptions = computed(() => {
  if (isEnum.value) return (props.field.options?.options || []).map(o => ({ id: o.id, label: o.label, color: o.color }))
  if (isMember.value) return (members.value || []).map(m => ({ id: m.id, label: m.name }))
  return []
})
const filteredOptions = computed(() => {
  const k = kw.value.trim().toLowerCase()
  return k ? listOptions.value.filter(o => String(o.label).toLowerCase().includes(k)) : listOptions.value
})

function toggle(id) {
  setSelected(selected.value.includes(id) ? selected.value.filter(x => x !== id) : [...selected.value, id])
}
function setSelected(v) {
  selected.value = v
  commit()
}
function onValue(v) {
  value.value = v
  commit()
}
function onOpChange() {
  commit()
}
function isEmpty(v) {
  return v == null || v === '' || (Array.isArray(v) && !v.length)
}
function commit() {
  // 值空（需取值时）→ 该字段无有效条件
  if (needsValue.value) {
    const v = (isEnum.value || isMember.value) ? selected.value : value.value
    if (isEmpty(v)) { emit('change', null); return }
    emit('change', { fieldId: props.field.field_name, operator: op.value, value: isEmpty(v) ? undefined : v })
    return
  }
  emit('change', { fieldId: props.field.field_name, operator: op.value, value: undefined })
}
function remove() { emit('change', null) }
</script>

<style scoped>
.ffp { display: flex; flex-direction: column; gap: 8px; min-width: 240px; }
.ffp-head { display: flex; align-items: center; gap: 8px; }
.ffp-head b { font-size: 14px; }
.ffp-scope { font-size: 11px; color: var(--st-text-3); background: var(--st-bg-hover); border-radius: 999px; padding: 2px 8px; }
.ffp-op { width: 130px; }
.ffp-search :deep(.el-input__wrapper) { box-shadow: none; background: var(--st-bg-hover); }
.ffp-count { display: flex; justify-content: space-between; font-size: 12px; color: var(--st-text-3); }
.ffp-clear { cursor: pointer; color: var(--st-text-2); }
.ffp-clear:hover { color: var(--st-primary); }
.ffp-clear.dim { color: var(--st-disabled); cursor: default; }
.ffp-list { display: flex; flex-direction: column; gap: 2px; max-height: 220px; overflow: auto; }
.ffp-item { display: flex; align-items: center; gap: 8px; padding: 4px 2px; cursor: pointer; border-radius: 4px; }
.ffp-item:hover { background: var(--st-bg-hover); }
.ffp-tag { border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.ffp-name { font-size: 13px; }
.ffp-empty { font-size: 12px; color: var(--st-text-4); text-align: center; padding: 8px 0; }
.ffp-foot { border-top: 1px solid var(--st-border); padding-top: 6px; }
.ffp-del { font-size: 12px; color: var(--el-color-danger); cursor: pointer; }
</style>
