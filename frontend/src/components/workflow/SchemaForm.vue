<template>
  <!-- LLM 处理节点的任务预设：选中自动填充提示词骨架，可再改 -->
  <div v-if="nodeType === 'llm_transform'" class="preset-row">
    <el-select size="small" placeholder="从任务模板填充（可选）" clearable :model-value="null" @change="applyPreset">
      <el-option v-for="p in AI_PRESETS" :key="p.label" :label="p.label" :value="p.label" />
    </el-select>
  </div>
  <el-form label-position="top" size="small" class="schema-form">
    <template v-for="(spec, key) in properties" :key="key">
    <el-form-item v-if="showField(key)" :required="required.includes(key)">
      <template #label>
        <span>{{ titleOf(key, spec) }}</span>
        <el-tooltip v-if="spec.description" :content="spec.description" placement="top">
          <el-icon class="hint-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>

      <!-- 结构化筛选条件 -->
      <FiltersEditor v-if="key === 'filters' || key === 'match_filters'" :key="`flt-${fieldsLoading}`"
        :model-value="cfg[key]" :fields="tableFields" :vars="vars"
        @update:model-value="set(key, $event)" />
      <!-- 条件分支节点的 rules：与 logic 联合编辑；字段是判断对象里的键，用变量选择器提取 -->
      <FiltersEditor v-else-if="key === 'rules'" :key="`flt-${fieldsLoading}`"
        :model-value="{ logic: cfg.logic || 'AND', rules: cfg.rules || [] }"
        :fields="tableFields" :vars="vars" @update:model-value="setRules" />
      <!-- 多路分支节点的 cases -->
      <CasesEditor v-else-if="key === 'cases'" :key="`cs-${fieldsLoading}`" :model-value="cfg[key]"
        :fields="tableFields" :vars="vars" @update:model-value="set(key, $event)" />
      <!-- 汇总统计节点的统计项 -->
      <AggsEditor v-else-if="key === 'aggs'" :model-value="cfg[key]" :fields="tableFields"
        @update:model-value="set(key, $event)" />
      <!-- 字段赋值 -->
      <FieldMappingEditor v-else-if="key === 'field_mapping'" :key="`fm-${fieldsLoading}`" :model-value="cfg[key]"
        :fields="tableFields" :vars="vars" @update:model-value="set(key, $event)" />
      <!-- 逐条处理的记录列表：只给列表型变量（records/groups 输出），并提示循环体怎么引用当前条目 -->
      <template v-else-if="key === 'items'">
        <TemplateInput :rows="3" :model-value="cfg[key]" :vars="listVars"
          placeholder="必须是列表——点下方「插入变量」选上游节点的「记录列表」输出"
          @update:model-value="set(key, $event)" />
        <div v-if="nodeId" class="field-hint">
          下一节点里用 <code>{{ `{nodes.${nodeId}.item.字段名}` }}</code> 引用当前条目
        </div>
      </template>
      <!-- 记录/记录列表：整体模板注入 -->
      <TemplateInput v-else-if="key === 'record' || key === 'records'" :rows="3" :model-value="cfg[key]" :vars="vars"
        placeholder="整体引用，如 {trigger.record} 或 {nodes.q.records}，也可点下方「插入变量」"
        @update:model-value="set(key, $event)" />
      <!-- 审批人 id 列表 -->
      <el-input v-else-if="key === 'approver_user_ids'" :model-value="(cfg[key] || []).join(',')"
        placeholder="用户 id，逗号分隔；留空 = 工作流归属人" @update:model-value="setIds(key, $event)" />
      <!-- 排序/去重/分组字段：输入框 + 选择按钮。排序字段可插变量（渲染后是列名）；
           去重/分组字段只给表字段（变量渲染出来是"值"不是"键名"，给了只会误导） -->
      <div v-else-if="['order_by', 'field', 'group_by'].includes(key)" class="ob-row">
        <el-input :model-value="cfg[key]" clearable
          :placeholder="key === 'order_by' ? '字段名，或点右侧选择（默认按 ID 倒序）' : '记录里的字段名，如 customer'"
          @update:model-value="set(key, $event)" />
        <VariablePicker compact :title="key === 'order_by' ? '选择字段或变量' : '选择字段'"
          empty-text="未找到上游表的字段——请先把查询记录节点连线到本节点"
          :groups="key === 'order_by' ? fieldPickGroups : fieldOnlyGroups" @insert="set(key, $event)" />
      </div>
      <!-- 数据表 / 模型供应商 / 子流程选择器 -->
      <el-select v-else-if="spec.format === 'table-ref'" :model-value="cfg[key]" filterable placeholder="选择数据表"
        @update:model-value="set(key, $event)">
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <el-select v-else-if="spec.format === 'workflow-ref'" :model-value="cfg[key]" filterable placeholder="选择子流程"
        @update:model-value="set(key, $event)">
        <el-option v-for="w in workflows" :key="w.id" :label="w.name" :value="w.id" />
      </el-select>
      <el-select v-else-if="spec.format === 'provider-ref'" :model-value="cfg[key]" clearable placeholder="默认供应商"
        @update:model-value="set(key, $event)">
        <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <!-- 模板 / 多行文本 -->
      <TemplateInput v-else-if="spec.format === 'template' || spec.format === 'textarea'" :rows="5"
        :model-value="cfg[key]" :vars="vars" placeholder="可直接输入，或点下方「插入变量」选择上游数据"
        @update:model-value="set(key, $event)" />
      <!-- 站内通知接收人：好友/群组选择器 -->
      <NotifyTargetPicker v-else-if="key === 'notify_targets'" :model-value="cfg[key]"
        @update:model-value="set(key, $event)" />
      <!-- 枚举 -->
      <el-select v-else-if="spec.enum" :model-value="cfg[key]" @update:model-value="set(key, $event)">
        <el-option v-for="(v, i) in spec.enum" :key="v" :label="(spec.enumNames || [])[i] || v" :value="v" />
      </el-select>
      <!-- 布尔 / 数字 -->
      <el-switch v-else-if="spec.type === 'boolean'" :model-value="cfg[key]" @update:model-value="set(key, $event)" />
      <el-input-number v-else-if="spec.type === 'integer' || spec.type === 'number'" :model-value="cfg[key]"
        :min="spec.minimum" :max="spec.maximum" controls-position="right" @update:model-value="set(key, $event)" />
      <!-- 对象/数组：JSON 编辑器（格式化 + 插入变量） -->
      <JsonInput v-else-if="spec.type === 'object' || spec.type === 'array'" :model-value="cfg[key]" :vars="vars"
        @update:model-value="set(key, $event)" />
      <el-input v-else :model-value="cfg[key]" @update:model-value="set(key, $event)" />
    </el-form-item>
    </template>
  </el-form>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { getTable } from '../../api'
import FiltersEditor from './FiltersEditor.vue'
import FieldMappingEditor from './FieldMappingEditor.vue'
import TemplateInput from './TemplateInput.vue'
import CasesEditor from './CasesEditor.vue'
import AggsEditor from './AggsEditor.vue'
import VariablePicker from './VariablePicker.vue'
import NotifyTargetPicker from './NotifyTargetPicker.vue'
import JsonInput from './JsonInput.vue'

// 发送通知节点：按通道决定接收人相关字段的显隐（站内通知→人员选择器，邮件/短信→接收人，机器人→Webhook 地址）
function showField(key) {
  if (props.nodeType !== 'send_message') return true
  const ch = cfg.channel || 'notify'
  if (key === 'notify_targets') return ch === 'notify'
  if (key === 'recipients') return ch === 'email' || ch === 'sms'
  if (key === 'webhook_url') return ['webhook', 'wecom', 'dingtalk'].includes(ch)
  return true
}
function titleOf(key, spec) {
  if (props.nodeType === 'send_message' && key === 'recipients') {
    return cfg.channel === 'sms' ? '接收手机号' : '接收邮箱'
  }
  return spec.title || key
}

// LLM 处理节点的任务预设：选中后填充 prompt/system/output_format 骨架
const AI_PRESETS = [
  {
    label: '文本分类',
    value: {
      prompt: '请把以下内容分类到其中之一：【类别一 / 类别二 / 类别三】，并给出一句话理由。\n输出 JSON：{"category": "类别名", "reason": "理由"}\n\n内容：{在此插入要分类的内容}',
      system: '你是一个严谨的文本分类器，只输出 JSON。',
      output_format: 'json',
    },
  },
  {
    label: '信息提取',
    value: {
      prompt: '请从以下内容中提取关键信息，输出 JSON：{"key1": "值", "key2": "值"}（按需要修改要提取的字段）。\n\n内容：{在此插入原文}',
      system: '你是一个信息提取助手，只输出 JSON，没有的字段填 null。',
      output_format: 'json',
    },
  },
  {
    label: '摘要总结',
    value: {
      prompt: '请把以下内容总结成 3 句话以内的摘要，突出重点数据：\n\n{在此插入内容}',
      system: '你是一个简洁的摘要助手。',
      output_format: 'text',
    },
  },
  {
    label: '情感分析',
    value: {
      prompt: '请判断以下内容的情感倾向（正面/负面/中性）和紧急程度（高/中/低）。\n输出 JSON：{"sentiment": "...", "urgency": "...", "reason": "一句话理由"}\n\n内容：{在此插入内容}',
      system: '你是一个情感分析助手，只输出 JSON。',
      output_format: 'json',
    },
  },
]

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  modelValue: { type: Object, default: () => ({}) },
  tables: { type: Array, default: () => [] },
  providers: { type: Array, default: () => [] },
  // 节点自身没有 table_id 时（如条件分支），由父组件沿上游推导的兜底表
  fallbackTableId: { type: Number, default: null },
  // 可插入的模板变量分组（上游节点输出 + 触发器），由父组件按画布连线推导
  vars: { type: Array, default: () => [] },
  // 节点类型（用于 LLM 节点显示任务预设等类型相关 UI）
  nodeType: { type: String, default: '' },
  // 节点 id（逐条处理节点的引用提示用，如 {nodes.loop_1.item.xxx}）
  nodeId: { type: String, default: '' },
  // 可选子流程清单（子流程调用节点的下拉数据源）
  workflows: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const properties = computed(() => props.schema?.properties || {})
const required = computed(() => props.schema?.required || [])

// 逐条处理的「记录列表」输入：只保留列表型变量（查询/更新的记录列表、汇总的分组列表），
// 避免用户选到单条记录或计数这类标量
const listVars = computed(() =>
  props.vars
    .map((g) => ({ ...g, items: g.items.filter((it) => /\.(records|groups)$/.test(it.expr)) }))
    .filter((g) => g.items.length)
)

// 字段引用类控件需要目标表的字段列表
// 注意：必须在下面的 immediate watch 之前声明——immediate watch 在 setup 中同步执行，
// 若声明在后面，首次执行会撞 TDZ（Cannot access before initialization），字段永远加载不上
const tableFields = ref([])
const fieldsCache = new Map()
// 字段加载中标记：加载完成后变更 :key 强制重渲染字段控件，
// 否则 el-select 会缓存异步窗口期渲染的兜底 label（“xxx（未知字段）”）不刷新
const fieldsLoading = ref(false)
// 排序/去重/分组字段的插入面板：表字段（插字段名，引擎按列名处理）+ 变量分组（插 {表达式}）
// 去重/分组节点自身没有 table_id，tableFields 来自上游推导的兜底表（如上游查询节点的表）
const fieldPickGroups = computed(() => {
  const groups = []
  if (tableFields.value.length) {
    groups.push({
      title: '表字段',
      items: [
        ...tableFields.value.map((f) => ({ label: f.label, expr: f.field_name })),
        { label: 'ID', expr: 'id' },
        { label: '创建时间', expr: 'created_at' },
        { label: '更新时间', expr: 'updated_at' },
      ],
    })
  }
  return [...groups, ...props.vars]
})
// 去重/分组字段：只给表字段（插键名），不给变量分组
const fieldOnlyGroups = computed(() => fieldPickGroups.value.filter((g) => g.title === '表字段'))
async function loadFields(tableId) {
  if (!tableId) { tableFields.value = []; return }
  if (fieldsCache.has(tableId)) { tableFields.value = fieldsCache.get(tableId); return }
  fieldsLoading.value = true
  try {
    const t = await getTable(tableId)
    fieldsCache.set(tableId, t.fields || [])
    tableFields.value = t.fields || []
  } catch { tableFields.value = [] } finally { fieldsLoading.value = false }
}

const cfg = reactive({})
watch(() => props.modelValue, (v) => {
  Object.keys(cfg).forEach((k) => delete cfg[k])
  Object.assign(cfg, v || {})
  loadFields(cfg.table_id || props.fallbackTableId)
}, { immediate: true, deep: true })

// 兜底表变化（如画布连线改动）且节点自身没选表时，重新加载字段
watch(() => props.fallbackTableId, (v) => {
  if (!cfg.table_id) loadFields(v)
})

function set(key, value) {
  cfg[key] = value
  if (key === 'table_id') loadFields(value || props.fallbackTableId)
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

// AI 任务预设：把预设的 prompt/system/output_format 一次性填入配置
function applyPreset(label) {
  const p = AI_PRESETS.find((x) => x.label === label)
  if (!p) return
  Object.assign(cfg, p.value)
  emit('update:modelValue', { ...cfg })
}

</script>

<style scoped>
.preset-row { margin-bottom: 10px; }
.preset-row .el-select { width: 100%; }
.ob-row { display: flex; align-items: center; gap: 6px; }
.ob-row .el-select, .ob-row .el-input { flex: 1; }
.hint-icon { margin-left: 4px; color: #c0c4cc; vertical-align: -2px; cursor: help; }
.schema-form :deep(.el-form-item) { margin-bottom: 14px; }
.schema-form :deep(.el-form-item__label) { padding-bottom: 2px !important; font-size: 12px; }
.field-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.field-hint code { background: #f5f7fa; border: 1px solid #e4e7ed; border-radius: 4px; padding: 1px 5px; }
</style>
