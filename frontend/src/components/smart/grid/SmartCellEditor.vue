<template>
  <!-- 编辑态挂载器（spike 版：内联输入 + 单选下拉，验证提交策略） -->
  <el-select
    v-if="field.field_type === 'singleSelect'"
    v-model="draft" size="small" class="cell-editor"
    :teleported="false" automatic-dropdown
    @change="commit" @visible-change="(vis) => !vis && $emit('cancel')"
  >
    <el-option v-for="o in (field.options?.options || [])" :key="o.id" :label="o.label" :value="o.id" />
  </el-select>
  <el-input
    v-else v-model="draft" size="small" class="cell-editor" autofocus
    @blur="commit" @keyup.enter="commit" @keyup.esc="$emit('cancel')"
  />
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
})
const emit = defineEmits(['commit', 'cancel'])

const draft = ref(props.record[props.field.field_name] ?? '')

function commit() {
  emit('commit', draft.value === '' ? null : draft.value)
}
</script>

<style scoped>
.cell-editor { width: 100%; }
.cell-editor :deep(.el-input__wrapper) { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
</style>
