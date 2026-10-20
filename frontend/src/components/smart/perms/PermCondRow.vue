<template>
  <!-- 权限行条件 / 自动化过滤条件共用的一行：字段 ▾ ｜ 运算符 ▾ ｜ 值 ｜ ⊖
       人员类字段（人员/创建人/最后编辑人）值可选「查看者本人」（$viewer，§13.3），对齐参照 内容权限-设计可编辑行条件.png -->
  <div class="pcr">
    <!-- 字段：统一「选择字段」面板（编组可折叠） -->
    <TbFieldSelect :model-value="cond.fieldId" :fields="fields" :column-groups="columnGroups" class="pcr-field" @update:model-value="onField" />
    <el-select v-if="field && !memberLike" :model-value="cond.operator" class="pcr-op" :teleported="teleported"
               @update:model-value="(v) => emit('update', { ...cond, operator: v })">
      <el-option v-for="op in ops" :key="op" :value="op" :label="opLabel(field, op)" />
    </el-select>
    <div v-if="field && needsValue" class="pcr-val">
      <ConditionValue :field="field" :operator="cond.operator" :value="cond.value"
                      @update="(v) => emit('update', { ...cond, value: v })" />
    </div>
    <div v-else-if="!field" class="pcr-val pcr-ph">请先选择字段</div>
    <span class="pcr-del st-icon-action" data-smart-tip="删除条件" @click="emit('remove')"><StIcon name="minus-circle" :size="18" /></span>
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, inject, provide } from 'vue'
import StIcon from '../icons/StIcon.vue'
import TbFieldSelect from '../panels/TbFieldSelect.vue'
import ConditionValue from '../panels/ConditionValue.vue'
import { filterOpsOf, NO_VALUE_OPS, opLabel } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  columnGroups: { type: Array, default: null },   // 字段来自其他表时传 []（不套用本表编组）
  cond: { type: Object, required: true },
  fields: { type: Array, default: () => [] },
  allowViewer: { type: Boolean, default: false },   // 人员类值是否提供「查看者本人」
  teleported: { type: Boolean, default: false },
})
const emit = defineEmits(['update', 'remove'])

const MEMBER_LIKE = ['member', 'createdBy', 'lastModifiedBy']
const field = computed(() => props.fields.find(f => f.field_name === props.cond.fieldId))
const memberLike = computed(() => MEMBER_LIKE.includes(field.value?.field_type))
const ops = computed(() => (field.value ? filterOpsOf(field.value) : []))
const needsValue = computed(() => !NO_VALUE_OPS.includes(props.cond.operator))

// 人员目录注入「查看者本人」虚拟项（ConditionValue 从 smartMembers 取人员候选）
const members = inject('smartMembers', { value: [] })
if (props.allowViewer) {
  provide('smartMembers', computed(() => [{ id: '$viewer', name: '查看者本人' }, ...(members.value || [])]))
}

function onField(fn) {
  const f = props.fields.find(x => x.field_name === fn)
  const ml = MEMBER_LIKE.includes(f?.field_type)
  const op = ml ? 'contains' : (filterOpsOf(f)[0] || 'eq')
  emit('update', { ...props.cond, fieldId: fn, operator: op, value: ml && props.allowViewer ? ['$viewer'] : undefined })
}
</script>

<style scoped>
.pcr { display: flex; align-items: center; gap: 6px; }
.pcr-field { width: 180px; flex: none; }
.pcr-op { width: 120px; flex: none; }
.pcr-val { flex: 1; min-width: 0; }
.pcr-ph { font-size: 13px; color: var(--st-text-4); padding-left: 8px; }
.pcr-opt { display: inline-flex; align-items: center; gap: 6px; }
.pcr-opt .st-icon { color: var(--st-text-2); }
.pcr-del { display: inline-flex; color: var(--st-text-4); cursor: pointer; flex: none; }
.pcr-del:hover { color: var(--el-color-danger); }
</style>
