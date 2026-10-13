<template>
  <!-- 记录详情抽屉（设计文档 §7.3）：全字段纵向展示/编辑 + 上一条/下一条 -->
  <el-drawer v-model="visibleModel" :title="title" size="480px" class="record-detail" >
    <div v-if="record" class="detail">
      <div class="nav">
        <el-button size="small" :disabled="!hasPrev" @click="$emit('nav', -1)">∧ 上一条</el-button>
        <el-button size="small" :disabled="!hasNext" @click="$emit('nav', 1)">∨ 下一条</el-button>
      </div>
      <div v-for="f in fields" :key="f.field_name" class="d-row">
        <div class="d-label"><span class="d-icon">{{ regOf(f).icon }}</span>{{ f.label }}</div>
        <div class="d-value">
          <SmartCell v-if="regOf(f).readonly" :field="f" :record="record" />
          <component v-else :is="editorFor(f)" :field="f" :record="record"
                     @commit="(v) => $emit('cell-commit', { row: record, field: f, value: v })" />
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'
import SmartCell from '../grid/SmartCell.vue'
import SmartCellEditor from '../grid/SmartCellEditor.vue'
import { regOf } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  record: Object,
  fields: { type: Array, default: () => [] },
  hasPrev: Boolean,
  hasNext: Boolean,
})
const emit = defineEmits(['close', 'nav', 'cell-commit', 'update:visible'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

const title = computed(() => {
  if (!props.record) return ''
  const first = props.fields[0]
  return props.record[first?.field_name] || `#${props.record.id}`
})
const editorFor = () => SmartCellEditor
</script>

<style scoped>
.detail { display: flex; flex-direction: column; gap: 4px; }
.nav { display: flex; gap: 8px; margin-bottom: 8px; }
.d-row { display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.d-label { width: 120px; color: var(--el-text-color-secondary); font-size: 13px; display: flex; gap: 6px; align-items: center; }
.d-icon { color: var(--el-color-primary); }
.d-value { flex: 1; }
</style>
