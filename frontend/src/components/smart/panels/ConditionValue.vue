<template>
  <!-- 条件值编辑器：按字段类型分发（单选/多选=选项勾选，数字=数字框，日期=日期，其余=文本） -->
  <el-select :teleported="false" v-if="isEnum" v-model="val" multiple filterable size="small" class="val-editor"
             placeholder="请选择" @change="$emit('update', val)">
    <el-option v-for="o in (field?.options?.options || [])" :key="o.id" :value="o.id" :label="o.label" />
  </el-select>
  <el-select :teleported="false" v-else-if="isMember" v-model="val" multiple filterable size="small" class="val-editor"
             placeholder="请选择成员" @change="$emit('update', val)">
    <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
  </el-select>
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

const props = defineProps({ field: Object, operator: String, value: [String, Number, Array] })
defineEmits(['update'])

const members = inject('smartMembers', { value: [] })
const val = ref(props.value ?? (['singleSelect', 'multiSelect', 'member'].includes(props.field?.field_type) ? [] : null))
watch(() => props.value, (v) => { val.value = v })

const ft = computed(() => props.field?.field_type)
const isEnum = computed(() => ['singleSelect', 'multiSelect'].includes(ft.value))
const isMember = computed(() => ['member', 'createdBy', 'lastModifiedBy'].includes(ft.value))
const isNumber = computed(() => ['number', 'percent', 'currency', 'progress'].includes(ft.value))
const isDate = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(ft.value)
  && !['today', 'pastDays', 'withinDays'].includes(props.operator))
const isRelativeDate = computed(() => isDate.value && ['pastDays', 'withinDays'].includes(props.operator))
</script>

<style scoped>
.val-editor { flex: 1; min-width: 120px; }
</style>
