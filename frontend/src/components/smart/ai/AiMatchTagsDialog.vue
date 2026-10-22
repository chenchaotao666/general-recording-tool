<template>
  <!-- AI 匹配标签（§18 V3）：为单选/多选列按依据字段内容批量匹配标签，可自动新建标签 -->
  <el-dialog :model-value="visible" :title="`AI 匹配标签 · ${field?.label || ''}`" width="480px" append-to-body
             @update:model-value="emit('close')">
    <div class="amt">
      <div class="amt-l">根据以下字段的内容匹配「{{ field?.label }}」</div>
      <el-select v-model="sources" multiple filterable placeholder="选择依据字段" class="amt-sel">
        <el-option v-for="f in candidates" :key="f.field_name" :value="f.field_name" :label="f.label" />
      </el-select>
      <el-checkbox v-model="onlyEmpty">仅处理「{{ field?.label }}」为空的记录</el-checkbox>
      <el-checkbox v-model="allowNew">没有合适的标签时允许 AI 新建标签</el-checkbox>
      <div class="amt-tip">单次最多处理 200 条记录；AI 写入的单元格「最后编辑人」显示为 AI 生成。</div>
    </div>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="loading" :disabled="!sources.length" @click="run">开始匹配</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { smartAiMatchTags } from '../../../api/index.js'

const props = defineProps({ visible: Boolean, tableId: Number, field: Object, fields: { type: Array, default: () => [] } })
const emit = defineEmits(['close', 'done'])
const sources = ref([])
const onlyEmpty = ref(true)
const allowNew = ref(true)
const loading = ref(false)
const candidates = computed(() => props.fields.filter(f => f.field_name !== props.field?.field_name
  && ['text', 'singleSelect', 'multiSelect', 'url', 'ai', 'formula', 'lookup'].includes(f.field_type)))
watch(() => props.visible, (v) => {
  if (v) sources.value = candidates.value.filter(f => f.field_type === 'text').slice(0, 1).map(f => f.field_name)
})

async function run() {
  loading.value = true
  try {
    const r = await smartAiMatchTags(props.tableId, props.field.field_name,
      { source_fields: sources.value, only_empty: onlyEmpty.value, allow_new: allowNew.value })
    ElMessage.success(`已为 ${r.updated} 条记录匹配标签${r.created_options ? `，新建 ${r.created_options} 个标签` : ''}`)
    emit('done')
    emit('close')
  } catch (e) {
    ElMessage.error(e.message || '匹配失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.amt { display: flex; flex-direction: column; gap: 12px; }
.amt-l { font-size: var(--st-font-size); color: var(--st-text-2); }
.amt-sel { width: 100%; }
.amt-tip { font-size: var(--st-font-size); color: var(--st-text-4); }
</style>
