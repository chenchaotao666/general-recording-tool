<template>
  <el-form label-position="top" size="small" class="schema-form">
    <el-form-item v-for="(spec, key) in properties" :key="key" :required="required.includes(key)">
      <template #label>
        <span>{{ spec.title || key }}</span>
        <el-tooltip v-if="spec.description" :content="spec.description" placement="top">
          <el-icon class="hint-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>

      <!-- 结构化筛选条件 -->
      <FiltersEditor v-if="key === 'filters' || key === 'match_filters'" :model-value="cfg[key]" :fields="tableFields"
        @update:model-value="set(key, $event)" />
      <!-- 条件分支节点的 rules：与 logic 联合编辑 -->
      <FiltersEditor v-else-if="key === 'rules'" :model-value="{ logic: cfg.logic || 'AND', rules: cfg.rules || [] }"
        :fields="tableFields" @update:model-value="setRules" />
      <!-- 字段赋值 -->
      <FieldMappingEditor v-else-if="key === 'field_mapping'" :model-value="cfg[key]" :fields="tableFields"
        @update:model-value="set(key, $event)" />
      <!-- 记录对象：整体模板注入 -->
      <el-input v-else-if="key === 'record'" type="textarea" :rows="2" :model-value="cfg[key]"
        placeholder="整体引用，如 {trigger.record} 或 {nodes.q.records.0}" @update:model-value="set(key, $event)" />
      <!-- 审批人 id 列表 -->
      <el-input v-else-if="key === 'approver_user_ids'" :model-value="(cfg[key] || []).join(',')"
        placeholder="用户 id，逗号分隔；留空 = 工作流归属人" @update:model-value="setIds(key, $event)" />
      <!-- 排序字段：从目标表字段中选（显示中文名） -->
      <el-select v-else-if="key === 'order_by'" :model-value="cfg[key]" clearable filterable
        placeholder="默认按 ID 倒序" @update:model-value="set(key, $event)">
        <el-option v-for="f in tableFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
        <el-option label="ID" value="id" />
        <el-option label="创建时间" value="created_at" />
        <el-option label="更新时间" value="updated_at" />
      </el-select>
      <!-- 数据表 / 模型供应商选择器 -->
      <el-select v-else-if="spec.format === 'table-ref'" :model-value="cfg[key]" filterable placeholder="选择数据表"
        @update:model-value="set(key, $event)">
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <el-select v-else-if="spec.format === 'provider-ref'" :model-value="cfg[key]" clearable placeholder="默认供应商"
        @update:model-value="set(key, $event)">
        <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <!-- 模板 / 多行文本 -->
      <el-input v-else-if="spec.format === 'template' || spec.format === 'textarea'" type="textarea" :rows="3"
        :model-value="cfg[key]" placeholder="支持 {trigger.xxx}、{nodes.节点id.xxx} 变量"
        @update:model-value="set(key, $event)" />
      <!-- 枚举 -->
      <el-select v-else-if="spec.enum" :model-value="cfg[key]" @update:model-value="set(key, $event)">
        <el-option v-for="(v, i) in spec.enum" :key="v" :label="(spec.enumNames || [])[i] || v" :value="v" />
      </el-select>
      <!-- 布尔 / 数字 -->
      <el-switch v-else-if="spec.type === 'boolean'" :model-value="cfg[key]" @update:model-value="set(key, $event)" />
      <el-input-number v-else-if="spec.type === 'integer' || spec.type === 'number'" :model-value="cfg[key]"
        :min="spec.minimum" :max="spec.maximum" controls-position="right" @update:model-value="set(key, $event)" />
      <!-- 对象/数组兜底：JSON 编辑 -->
      <el-input v-else-if="spec.type === 'object' || spec.type === 'array'" type="textarea" :rows="3"
        :model-value="jsonText(key)" placeholder='JSON，如 {"key": "value"}' @update:model-value="setJson(key, $event)" />
      <el-input v-else :model-value="cfg[key]" @update:model-value="set(key, $event)" />
    </el-form-item>
  </el-form>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { getTable } from '../../api'
import FiltersEditor from './FiltersEditor.vue'
import FieldMappingEditor from './FieldMappingEditor.vue'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  modelValue: { type: Object, default: () => ({}) },
  tables: { type: Array, default: () => [] },
  providers: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const properties = computed(() => props.schema?.properties || {})
const required = computed(() => props.schema?.required || [])

const cfg = reactive({})
watch(() => props.modelValue, (v) => {
  Object.keys(cfg).forEach((k) => delete cfg[k])
  Object.assign(cfg, v || {})
  loadFields(cfg.table_id)
}, { immediate: true, deep: true })

function set(key, value) {
  cfg[key] = value
  if (key === 'table_id') loadFields(value)
  emit('update:modelValue', { ...cfg })
}
function setRules(v) {
  cfg.logic = v.logic
  cfg.rules = v.rules
  emit('update:modelValue', { ...cfg })
}
function setIds(key, text) {
  const ids = String(text || '').replace(/，/g, ',').split(',').map((s) => s.trim()).filter(Boolean)
    .map(Number).filter((n) => Number.isInteger(n))
  set(key, ids)
}

// 字段引用类控件需要目标表的字段列表
const tableFields = ref([])
const fieldsCache = new Map()
async function loadFields(tableId) {
  if (!tableId) { tableFields.value = []; return }
  if (fieldsCache.has(tableId)) { tableFields.value = fieldsCache.get(tableId); return }
  try {
    const t = await getTable(tableId)
    fieldsCache.set(tableId, t.fields || [])
    tableFields.value = t.fields || []
  } catch { tableFields.value = [] }
}

const jsonErr = reactive({})
function jsonText(key) {
  const v = cfg[key]
  return v === undefined || v === null ? '' : (typeof v === 'string' ? v : JSON.stringify(v))
}
function setJson(key, text) {
  if (!String(text).trim()) { set(key, undefined); return }
  try {
    set(key, JSON.parse(text))
    jsonErr[key] = ''
  } catch {
    jsonErr[key] = 'JSON 格式错误'
  }
}
</script>

<style scoped>
.hint-icon { margin-left: 4px; color: #c0c4cc; vertical-align: -2px; cursor: help; }
.schema-form :deep(.el-form-item) { margin-bottom: 14px; }
.schema-form :deep(.el-form-item__label) { padding-bottom: 2px !important; font-size: 12px; }
</style>
