<template>
  <!-- 条件值编辑器：按字段类型分发。
       单选/多选/人员=可搜索勾选清单（已选计数/清空/彩色标签，贴近多维表格筛选形态）；
       数字=数字框，日期=日期，其余=文本 -->
  <div v-if="isEnum || isMember" class="opt-editor">
    <div class="opt-head">
      <span class="opt-count">已选择 {{ val.length }} {{ isMember ? '人' : '项' }}</span>
      <span class="opt-head-right">
        <el-button link type="primary" size="small" :disabled="!val.length" @click="setVal([])">清空</el-button>
        <el-input v-model="kw" size="small" placeholder="搜索" clearable class="opt-search" />
      </span>
    </div>
    <div class="opt-list">
      <label v-for="o in filteredOptions" :key="o.id" class="opt-item">
        <el-checkbox :model-value="val.includes(o.id)" size="small" @change="toggle(o.id)" />
        <span v-if="isEnum" class="opt-tag"
              :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
        <span v-else class="opt-name">{{ o.label }}</span>
      </label>
      <div v-if="!filteredOptions.length" class="opt-empty">无匹配{{ isMember ? '成员' : '选项' }}</div>
    </div>
  </div>
  <el-input-number v-else-if="isNumber" v-model="val" size="small" class="val-editor"
                   @change="$emit('update', val)" />
  <el-date-picker v-else-if="isDate" v-model="val" type="date" value-format="YYYY-MM-DD" size="small"
                  class="val-editor" @change="$emit('update', val)" />
  <el-input-number v-else-if="isRelativeDate" v-model="val" size="small" class="val-editor"
                   :min="1" placeholder="天数" @change="$emit('update', val)" />
  <el-input v-else v-model="val" size="small" class="val-editor" placeholder="请输入"
            @input="$emit('update', val)" />
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({ field: Object, operator: String, value: [String, Number, Array] })
const emit = defineEmits(['update'])

const members = inject('smartMembers', { value: [] })
const ENUM_LIKE = ['singleSelect', 'multiSelect', 'member', 'createdBy', 'lastModifiedBy']
const initVal = (v, ft) => v ?? (ENUM_LIKE.includes(ft) ? [] : null)
const val = ref(initVal(props.value, props.field?.field_type))
// 外部 value 变化、或切换字段（value 会重置为 undefined）时归一化：
// 枚举/人员类必须是数组，否则模板 val.length 会在 null 上炸
watch([() => props.value, () => props.field?.field_type], ([v, ft]) => { val.value = initVal(v, ft) })

const ft = computed(() => props.field?.field_type)
const isEnum = computed(() => ['singleSelect', 'multiSelect'].includes(ft.value))
const isMember = computed(() => ['member', 'createdBy', 'lastModifiedBy'].includes(ft.value))
const isNumber = computed(() => ['number', 'percent', 'currency', 'progress'].includes(ft.value))
const isDate = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(ft.value)
  && !['today', 'pastDays', 'withinDays'].includes(props.operator))
const isRelativeDate = computed(() => isDate.value && ['pastDays', 'withinDays'].includes(props.operator))

// 勾选清单：枚举取字段选项（带颜色标签），人员取成员列表
const kw = ref('')
const listOptions = computed(() => {
  if (isEnum.value) return (props.field?.options?.options || []).map(o => ({ id: o.id, label: o.label, color: o.color }))
  if (isMember.value) return (members.value || []).map(m => ({ id: m.id, label: m.name }))
  return []
})
const filteredOptions = computed(() => {
  const k = kw.value.trim().toLowerCase()
  return k ? listOptions.value.filter(o => String(o.label).toLowerCase().includes(k)) : listOptions.value
})
function toggle(id) {
  const v = val.value.includes(id) ? val.value.filter(x => x !== id) : [...val.value, id]
  setVal(v)
}
function setVal(v) {
  val.value = v
  emit('update', v)
}
</script>

<style scoped>
.val-editor { flex: 1; min-width: 120px; }

.opt-editor { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 6px 8px; }
.opt-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.opt-count { font-size: 12px; color: var(--el-text-color-secondary); }
.opt-head-right { display: flex; align-items: center; gap: 6px; }
.opt-search { width: 110px; }
.opt-list { display: flex; flex-direction: column; gap: 2px; max-height: 180px; overflow: auto; }
.opt-item { display: flex; align-items: center; gap: 6px; padding: 2px 0; cursor: pointer; }
.opt-tag { border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.opt-name { font-size: 13px; }
.opt-empty { font-size: 12px; color: var(--el-text-color-placeholder); padding: 6px 0; text-align: center; }
</style>
