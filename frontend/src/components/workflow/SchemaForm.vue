<template>
  <!-- LLM 处理节点的提示词模板：选中自动填充提示词骨架，可再改 -->
  <div v-if="nodeType === 'llm_transform'" class="preset-row">
    <el-select size="small" placeholder="选择提示词模板（可选，填入后可修改）" clearable :model-value="null" @change="applyPreset">
      <el-option v-for="p in AI_PRESETS" :key="p.label" :label="p.label" :value="p.label" />
    </el-select>
  </div>
  <!-- 日期计算节点的偏移预设：一键填常用偏移（天/分钟） -->
  <div v-if="nodeType === 'date_calc'" class="preset-row">
    <span class="preset-label">快捷偏移：</span>
    <el-link v-for="p in OFFSET_PRESETS" :key="p.label" type="primary" size="small" class="preset-link"
      @click="applyOffset(p)">{{ p.label }}</el-link>
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
      <!-- 条件分支节点的 rules：与 logic 联合编辑；字段是判断对象里的键名（自由输入 + ⚡，
           ⚡ 面板列出判断对象的字段，由 recordFields 推导） -->
      <FiltersEditor v-else-if="key === 'rules'" :key="`flt-${fieldsLoading}`" field-free
        :model-value="{ logic: cfg.logic || 'AND', rules: cfg.rules || [] }"
        :fields="ruleFields" :vars="vars" @update:model-value="setRules" />
      <!-- 多路分支节点的 cases -->
      <CasesEditor v-else-if="key === 'cases'" :key="`cs-${fieldsLoading}`" :model-value="cfg[key]"
        :fields="ruleFields" :vars="vars" @update:model-value="set(key, $event)" />
      <!-- 汇总统计节点的统计项 -->
      <AggsEditor v-else-if="key === 'aggs'" :model-value="cfg[key]" :fields="tableFields"
        @update:model-value="set(key, $event)" />
      <!-- 字段赋值。注意不能加 :key 强制重挂载：重挂载会用 modelValue 重建本地行，
           「选了字段还没填值」（未 emit 过）的行会被丢光——用户看到的就是行突然消失 -->
      <FieldMappingEditor v-else-if="key === 'field_mapping'" :model-value="cfg[key]"
        :fields="tableFields" :vars="vars" @update:model-value="set(key, $event)" />
      <!-- 记录列表（去重/汇总统计/逐条处理）：下拉选列表型变量（上游 records/groups 输出），
           allow-create 兼容自定义表达式（如 {trigger.params.list}） -->
      <template v-else-if="key === 'records' || key === 'items'">
        <el-select :model-value="cfg[key]" size="small" filterable allow-create default-first-option
          style="width: 100%" placeholder="选择上游的记录列表，或输入变量表达式"
          no-data-text="没有列表型变量可选——请先连线一个「查询记录」节点（更新记录/去重/汇总统计的输出也行）"
          @update:model-value="set(key, $event)">
          <el-option v-for="o in listOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <div class="field-hint">必须是列表（查询/更新/去重/汇总统计的输出）；留空或填非标量执行时会报错</div>
        <div v-if="key === 'items' && nodeId" class="field-hint">
          下一节点里用 <code>{{ `{nodes.${nodeId}.item.字段名}` }}</code> 引用当前条目
        </div>
      </template>
      <!-- 条件/多路分支的「判断对象」：专用选择器（候选 = 循环当前条目/触发记录/上游记录），
           allow-create 保留手输；未配置过且能推导候选时自动填第一个。
           不带 clearable：必填字段清空无意义，且清空成 undefined 会被自动回填逻辑反复填回 -->
      <template v-else-if="key === 'record'">
        <el-select :model-value="cfg[key]" size="small" filterable allow-create default-first-option
          placeholder="选择要判断的记录，或输入变量表达式" @update:model-value="set(key, $event)">
          <el-option v-for="o in recordOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <div class="field-hint">要判断哪条记录：通常是刚触发流程的那条（触发记录）；循环体里选「当前条目」。下面规则里的「字段」填这条记录里的键名（如 urgency）</div>
      </template>
      <!-- 审批人：与站内通知接收人一致的人员选择器（好友/群组；空 = 工作流归属人） -->
      <NotifyTargetPicker v-else-if="key === 'approver_user_ids'" :model-value="cfg[key]"
        @update:model-value="set(key, $event)" />
      <!-- 排序/去重/分组字段：有表字段时下拉选（与筛选条件一致），allow-create 兼容模板变量和历史值；
           没有字段来源时退回输入框（排序字段可插变量，渲染后是列名；去重/分组只认记录键名）。
           排序字段与升降序合成一行（字段下拉 + 升/降序按钮组），order_desc 不再单列 -->
      <template v-else-if="['order_by', 'field', 'group_by'].includes(key)">
        <div v-if="tableFields.length" class="ob-combo">
          <el-select :model-value="cfg[key]" clearable filterable allow-create
            default-first-option class="ob-field"
            :placeholder="key === 'order_by' ? '选择排序字段（默认按 ID 倒序）' : '选择记录里的字段'"
            @update:model-value="set(key, $event)">
            <el-option v-for="f in tableFields" :key="f.field_name" :label="`${f.label}（${f.field_name}）`" :value="f.field_name" />
            <el-option label="ID" value="id" />
            <el-option label="创建时间" value="created_at" />
            <el-option label="更新时间" value="updated_at" />
          </el-select>
          <el-radio-group v-if="key === 'order_by'" :model-value="cfg.order_desc ?? true" size="small"
            @update:model-value="set('order_desc', $event)">
            <el-radio-button :value="true">降序</el-radio-button>
            <el-radio-button :value="false">升序</el-radio-button>
          </el-radio-group>
        </div>
        <div v-else class="ob-row">
          <el-input :model-value="cfg[key]" clearable
            :placeholder="key === 'order_by' ? '字段名（默认按 ID 倒序）' : '记录里的字段名，如 customer'"
            @update:model-value="set(key, $event)" />
          <VariablePicker compact :title="key === 'order_by' ? '选择字段或变量' : '选择字段'"
            empty-text="未找到上游表的字段——请先把查询记录节点连线到本节点"
            :groups="key === 'order_by' ? fieldPickGroups : fieldOnlyGroups" @insert="set(key, $event)" />
        </div>
      </template>
      <!-- 数据表 / 模型供应商 / 子流程选择器 -->
      <el-select v-else-if="spec.format === 'table-ref'" :model-value="cfg[key]" filterable placeholder="选择数据表"
        @update:model-value="set(key, $event)">
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <el-select v-else-if="spec.format === 'workflow-ref'" :model-value="cfg[key]" filterable placeholder="选择子流程"
        @update:model-value="set(key, $event)">
        <el-option v-for="w in workflows" :key="w.id" :label="w.name" :value="w.id" />
      </el-select>
      <el-select v-else-if="spec.format === 'report-ref'" :model-value="cfg[key]" filterable placeholder="选择报表"
        @update:model-value="set(key, $event)">
        <el-option v-for="r in reports" :key="r.id" :label="r.name" :value="r.id" />
      </el-select>
      <el-select v-else-if="spec.format === 'provider-ref'" :model-value="cfg[key]" clearable placeholder="默认供应商"
        @update:model-value="set(key, $event)">
        <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <!-- 邮件/短信接收人：标签式录入（回车添加、逐个校验格式），内部仍存逗号分隔字符串。
           不用模板框：接收人就是地址列表，不需要插入变量 -->
      <template v-else-if="key === 'recipients' && nodeType === 'send_message'">
        <el-select :model-value="recipientsList" multiple filterable allow-create default-first-option
          :placeholder="cfg.channel === 'sms' ? '输入手机号后回车，可添加多个' : '输入邮箱后回车，可添加多个'"
          style="width: 100%" @update:model-value="setRecipients">
          <el-option v-for="r in recipientsList" :key="r" :label="r" :value="r" />
        </el-select>
        <div class="field-hint">{{ cfg.channel === 'sms' ? '每个手机号一个标签，回车添加' : '每个邮箱一个标签，回车添加' }}</div>
      </template>
      <!-- 查询记录的 AI 筛选：结构化条件之后的自然语言精筛（LLM 分批判断候选） -->
      <template v-else-if="key === 'ai_filter' && nodeType === 'query_records'">
        <el-input type="textarea" :rows="2" :model-value="cfg[key]"
          placeholder="可选：用自然语言进一步筛选，如「语气明显负面的反馈」"
          @update:model-value="set(key, $event)" />
        <div class="field-hint">先按上面的筛选条件/排序/条数收窄候选，再由 AI 分批判断，最多判断前 200 条；会产生 token 消耗</div>
      </template>
      <!-- 查询记录的输出字段投影：多选表字段，留空 = 全部字段 -->
      <template v-else-if="key === 'fields' && nodeType === 'query_records'">
        <el-select :model-value="cfg[key] || []" multiple filterable clearable collapse-tags :max-collapse-tags="4"
          style="width: 100%" placeholder="留空 = 输出全部字段" @update:model-value="set(key, $event)">
          <el-option v-for="f in tableFields" :key="f.field_name" :label="`${f.label}（${f.field_name}）`" :value="f.field_name" />
          <el-option label="创建时间（created_at）" value="created_at" />
          <el-option label="更新时间（updated_at）" value="updated_at" />
        </el-select>
        <div class="field-hint">收窄输出字段可降低 AI 筛选/LLM 的 token 消耗、通知表格更清爽；id 总会保留。下游引用未选中的字段会拿到空值</div>
      </template>
      <!-- 模板 / 多行文本；日期计算的基准时间给快捷预设（映射 now 变量） -->
      <el-select v-else-if="key === 'base' && nodeType === 'date_calc'" :model-value="cfg[key]" size="small" filterable
        allow-create default-first-option clearable placeholder="留空 = 当前时间，或选快捷基准"
        @update:model-value="set(key, $event)">
        <el-option v-for="[label, v] in BASE_PRESETS" :key="label" :label="label" :value="v" />
      </el-select>
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
      <!-- 查询记录的条数上限：数字框 + 「不限制」勾选（= 0 返回全部，引擎侧支持） -->
      <template v-else-if="key === 'limit' && nodeType === 'query_records'">
        <div class="ob-combo">
          <el-input-number :model-value="cfg.limit === 0 ? undefined : cfg.limit" :min="1" :max="500"
            :disabled="cfg.limit === 0" controls-position="right" size="small" placeholder="条数"
            @update:model-value="set(key, $event ?? 100)" />
          <el-checkbox :model-value="cfg.limit === 0" size="small"
            @update:model-value="set(key, $event ? 0 : 100)">不限制</el-checkbox>
        </div>
        <div class="field-hint">默认 100 条，最大 500 条；不限制返回全部记录，数据量大时慎用</div>
      </template>
      <!-- 逐条处理的条数上限：数字框 + 「不限制」勾选（= 0 处理全部，引擎 1000 步总量兜底） -->
      <template v-else-if="key === 'max_items' && nodeType === 'foreach'">
        <div class="ob-combo">
          <el-input-number :model-value="cfg.max_items === 0 ? undefined : cfg.max_items" :min="1"
            :disabled="cfg.max_items === 0" controls-position="right" size="small" placeholder="条数"
            @update:model-value="set(key, $event ?? 50)" />
          <el-checkbox :model-value="cfg.max_items === 0" size="small"
            @update:model-value="set(key, $event ? 0 : 50)">不限制</el-checkbox>
        </div>
        <div class="field-hint">默认 50 条；不限制处理全部，列表很长时请先用上游查询/筛选收窄（引擎有单 Run 1000 步总量兜底）</div>
      </template>
      <!-- 布尔 / 数字 -->
      <el-switch v-else-if="spec.type === 'boolean'" :model-value="cfg[key]" @update:model-value="set(key, $event)" />
      <el-input-number v-else-if="spec.type === 'integer' || spec.type === 'number'" :model-value="cfg[key]"
        :min="spec.minimum" :max="spec.maximum" controls-position="right" @update:model-value="set(key, $event)" />
      <!-- LLM 的 JSON 输出键名：标签式录入，下游变量选择器会列出这些键 -->
      <el-select v-else-if="key === 'output_keys'" :model-value="cfg[key] || []" multiple filterable allow-create
        default-first-option placeholder="输入键名后回车，如 category、reason"
        @update:model-value="set(key, $event)" />
      <!-- HTTP 请求头：键值对行编辑器（不手写 JSON） -->
      <KvEditor v-else-if="key === 'headers' && nodeType === 'http_request'" :model-value="cfg[key]" :vars="vars"
        key-placeholder="Header 名，如 Authorization" @update:model-value="set(key, $event)" />
      <!-- HTTP 请求体：简单键值对用表单模式，嵌套结构切 JSON 模式 -->
      <template v-else-if="key === 'body' && nodeType === 'http_request'">
        <el-radio-group v-model="bodyMode" size="small" class="body-mode">
          <el-radio-button value="form">表单模式</el-radio-button>
          <el-radio-button value="json">JSON 模式</el-radio-button>
        </el-radio-group>
        <KvEditor v-if="bodyMode === 'form'" :model-value="cfg[key]" :vars="vars"
          key-placeholder="字段名" @update:model-value="set(key, $event)" />
        <JsonInput v-else :model-value="cfg[key]" :vars="vars" @update:model-value="set(key, $event)" />
      </template>
      <!-- 子流程传参：选定子流程后自动扫描它用到的 {trigger.params.xxx}，预填键名；值用多行文本框（内容可能较长） -->
      <template v-else-if="key === 'params' && nodeType === 'sub_workflow'">
        <KvEditor :model-value="cfg[key]" :vars="vars" :preset-keys="subParamKeys" value-textarea
          key-placeholder="参数名" value-placeholder="值（可较长），或点右侧插入变量"
          @update:model-value="set(key, $event)" />
        <div v-if="cfg.workflow_id && !subParamKeys.length" class="field-hint">所选子流程没有用到 {trigger.params.xxx} 变量，可不填</div>
      </template>
      <!-- Webhook/机器人地址：按通道给示例占位 + 获取路径提示 + URL 形态即时校验 -->
      <template v-else-if="key === 'webhook_url' && nodeType === 'send_message'">
        <el-input :model-value="cfg[key]" clearable :placeholder="webhookHint.placeholder"
          @update:model-value="set(key, $event)" />
        <div class="field-hint">{{ webhookHint.hint }}</div>
        <div v-if="cfg[key] && !/^https?:\/\//.test(cfg[key])" class="field-hint err">地址应以 http:// 或 https:// 开头</div>
      </template>
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
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { getTable, getWorkflow } from '../../api'
import FiltersEditor from './FiltersEditor.vue'
import FieldMappingEditor from './FieldMappingEditor.vue'
import TemplateInput from './TemplateInput.vue'
import CasesEditor from './CasesEditor.vue'
import AggsEditor from './AggsEditor.vue'
import VariablePicker from './VariablePicker.vue'
import NotifyTargetPicker from './NotifyTargetPicker.vue'
import JsonInput from './JsonInput.vue'
import { buildRecordOptions } from './judgeObject'
import KvEditor from './KvEditor.vue'

// 发送通知节点：按通道决定接收人相关字段的显隐（站内通知→人员选择器，邮件/短信→接收人，机器人→Webhook 地址）
function showField(key) {
  if (props.nodeType === 'send_message') {
    const ch = cfg.channel || 'notify'
    if (key === 'notify_targets') return ch === 'notify'
    if (key === 'recipients') return ch === 'email' || ch === 'sms'
    if (key === 'webhook_url') return ['webhook', 'wecom', 'dingtalk'].includes(ch)
  }
  // LLM 节点的 JSON 输出键名只在 JSON 格式下显示
  if (props.nodeType === 'llm_transform' && key === 'output_keys') {
    return (cfg.output_format || 'text') === 'json'
  }
  // order_desc 已并入排序字段行的「升/降序」按钮组，不再单列
  if (key === 'order_desc' && 'order_by' in properties.value) return false
  // 条件分支的「条件组合」（AND/OR）已在条件规则编辑器顶部集成（满足全部/任一），不再单列
  if (props.nodeType === 'condition' && key === 'logic') return false
  // 条件/多路分支的「关联数据表」：UI 上不再需要（规则字段已跟随判断对象推导；
  // 后端 schema 保留——存量配置与 AI 生成仍可用它做类型兜底）
  if (['condition', 'switch'].includes(props.nodeType) && key === 'table_id') return false
  // 推送报表的起止日期只在自定义区间时显示
  if (props.nodeType === 'push_report' && ['range_start', 'range_end'].includes(key)) {
    return cfg.range_mode === 'custom'
  }
  return true
}
function titleOf(key, spec) {
  if (props.nodeType === 'send_message' && key === 'recipients') {
    return cfg.channel === 'sms' ? '接收手机号' : '接收邮箱'
  }
  if (props.nodeType === 'send_message' && key === 'webhook_url') {
    return cfg.channel === 'webhook' ? 'Webhook 地址' : '机器人 Webhook 地址'
  }
  return spec.title || key
}

// 发送通知节点 webhook_url 的按通道提示：示例占位（看得出长什么样）+ 获取路径（知道去哪拿）
const WEBHOOK_HINTS = {
  webhook: {
    placeholder: 'https://你的服务器/hook',
    hint: '会向该地址 POST JSON：{workflow, run_id, title, content}；留空则使用「设置 → 通知渠道」里的默认 Webhook 地址',
  },
  wecom: {
    placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx',
    hint: '获取：企业微信群聊 → 右上角… → 群机器人 → 添加 → 复制 Webhook 地址；发送的是 text 文本消息',
  },
  dingtalk: {
    placeholder: 'https://oapi.dingtalk.com/robot/send?access_token=xxx',
    hint: '获取：钉钉群 → 群设置 → 机器人 → 添加「自定义」机器人 → 复制 Webhook；若安全设置选了「自定义关键词」，消息里必须包含该词（可把关键词设成工作流名）',
  },
}
const webhookHint = computed(() => WEBHOOK_HINTS[cfg.channel] || WEBHOOK_HINTS.webhook)

// LLM 处理节点的提示词模板：选中后填充 prompt/system/output_format 骨架；JSON 类模板连 output_keys 一起填
const AI_PRESETS = [
  {
    label: '文本分类',
    value: {
      prompt: '请把以下内容分类到其中之一：【类别一 / 类别二 / 类别三】，并给出一句话理由。\n输出 JSON：{"category": "类别名", "reason": "理由"}\n\n内容：{在此插入要分类的内容}',
      system: '你是一个严谨的文本分类器，只输出 JSON。',
      output_format: 'json',
      output_keys: ['category', 'reason'],
    },
  },
  {
    label: '信息提取',
    value: {
      prompt: '请从以下内容中提取关键信息，输出 JSON：{"key1": "值", "key2": "值"}（按需要修改要提取的字段）。\n\n内容：{在此插入原文}',
      system: '你是一个信息提取助手，只输出 JSON，没有的字段填 null。',
      output_format: 'json',
      output_keys: ['key1', 'key2'],
    },
  },
  {
    label: '摘要总结',
    value: {
      prompt: '请把以下内容总结成 3 句话以内的摘要，突出重点数据：\n\n{在此插入内容}',
      system: '你是一个简洁的摘要助手。',
      output_format: 'text',
      output_keys: [],   // 文本格式没有 JSON 键，清空避免下游变量选择器列出不会存在的键
    },
  },
  {
    label: '情感分析',
    value: {
      prompt: '请判断以下内容的情感倾向（正面/负面/中性）和紧急程度（高/中/低）。\n输出 JSON：{"sentiment": "...", "urgency": "...", "reason": "一句话理由"}\n\n内容：{在此插入内容}',
      system: '你是一个情感分析助手，只输出 JSON。',
      output_format: 'json',
      output_keys: ['sentiment', 'urgency', 'reason'],
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
  // 可选报表清单（推送报表节点的下拉数据源）
  reports: { type: Array, default: () => [] },
  // 条件/多路分支的条件规则字段（跟随判断对象，由父组件推导）；null = 退回表字段
  recordFields: { type: Array, default: null },
})
const emit = defineEmits(['update:modelValue'])

const properties = computed(() => props.schema?.properties || {})
const required = computed(() => props.schema?.required || [])

// 条件规则/分支条件行的字段来源：优先判断对象推导的字段，否则表字段
const ruleFields = computed(() =>
  (props.recordFields && props.recordFields.length) ? props.recordFields : tableFields.value
)

// 条件/多路分支「判断对象」的候选：循环当前条目 > 触发记录（含变更前）> 列表第一条 > 上游对象输出。
// 循环体里的判断几乎总是针对「当前条目」，所以 item 候选排最前（自动填充取第一个）；
// 构建逻辑与 AI 配置上下文共用（judgeObject.js）
const recordOptions = computed(() => buildRecordOptions(props.vars))

// 日期计算：基准时间快捷预设（映射内置 now 变量，留空 = 当前时间）
const BASE_PRESETS = [
  ['今天', '{now.today}'], ['昨天', '{now.yesterday}'], ['明天', '{now.tomorrow}'],
  ['本周一', '{now.week_start}'], ['上周一', '{now.last_week_start}'], ['上周日', '{now.last_week_end}'],
  ['本月 1 日', '{now.month_start}'], ['上月 1 日', '{now.last_month_start}'], ['上月最后一日', '{now.last_month_end}'],
]
const OFFSET_PRESETS = [
  { label: '+1 天', days: 1 }, { label: '+7 天', days: 7 }, { label: '-1 天', days: -1 }, { label: '-30 天', days: -30 },
  { label: '+30 分钟', minutes: 30 }, { label: '-15 分钟', minutes: -15 },
]

// 快捷偏移：一次设置天数和分钟（未涉及的档位清零，避免与上一次点击的残留叠加）
function applyOffset(p) {
  set('offset_days', p.days ?? 0)
  set('offset_hours', 0)
  set('offset_minutes', p.minutes ?? 0)
}

// 逐条处理/去重/汇总的「记录列表」输入：只保留列表型变量（查询/更新的记录列表、汇总的分组列表），
// 避免用户选到单条记录或计数这类标量。
// 注意表达式带结尾大括号（{nodes.q_1.records}），匹配时必须把 } 算进去——否则永远匹配为空
const listVars = computed(() =>
  props.vars
    .map((g) => ({ ...g, items: g.items.filter((it) => /\.(records|groups)\}+$/.test(it.expr)) }))
    .filter((g) => g.items.length)
)
// 「记录列表」下拉的扁平选项（「组名 · 条目」格式，与判断对象候选一致）
const listOptions = computed(() =>
  listVars.value.flatMap((g) => g.items.map((it) => ({ label: `${g.title} · ${it.label}`, value: it.expr })))
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

// HTTP 请求体的编辑模式（表单/JSON）。注意：下面的 cfg watch 是 immediate（setup 中同步执行），
// 这些状态必须先于它声明，否则首次执行撞 TDZ（Cannot access before initialization）
const bodyMode = ref('form')
let bodyModeInited = false
let lastSubWfId = undefined

// 切换节点时重置模式推断（组件实例跨节点复用）
watch(() => props.nodeId, () => { bodyModeInited = false })

// 子流程传参：扫描目标子流程全部节点配置里用到的 {trigger.params.键}，预填为键值行
const subParamKeys = ref([])
let subParamsSeq = 0
async function loadSubParams(wfId) {
  const seq = ++subParamsSeq
  if (!wfId) { subParamKeys.value = []; return }
  try {
    const wf = await getWorkflow(wfId)
    if (seq !== subParamsSeq) return   // 过期响应丢弃（用户连续切换子流程）
    const keys = new Set()
    const re = /\{\s*trigger\.params\.([^{}.\s]+)/g
    for (const m of JSON.stringify(wf.nodes || []).matchAll(re)) keys.add(m[1])
    subParamKeys.value = [...keys]
  } catch {
    if (seq === subParamsSeq) subParamKeys.value = []
  }
}

const cfg = reactive({})
watch(() => props.modelValue, (v) => {
  Object.keys(cfg).forEach((k) => delete cfg[k])
  Object.assign(cfg, v || {})
  loadFields(cfg.table_id || props.fallbackTableId)
  // schema 里带 default 的字段（条数上限 100、最多处理 50、超时 30s 等）打开面板即回填，
  // 让默认值可见、可改，而不是藏在后端
  const defaults = {}
  for (const [k, spec] of Object.entries(properties.value)) {
    if (cfg[k] === undefined && spec.default !== undefined) defaults[k] = spec.default
  }
  if (Object.keys(defaults).length) {
    Object.assign(cfg, defaults)
    emit('update:modelValue', { ...cfg })
  }
  // 判断对象从未配置过（null/undefined）且有候选时自动填第一个（通常是 {trigger.record}）；
  // 用户清空过（''）不反复回填
  if (['condition', 'switch'].includes(props.nodeType) && cfg.record == null && recordOptions.value.length) {
    set('record', recordOptions.value[0].value)
  }
  // 审批详情模板：首次配置给骨架（触发记录的前几个字段），有参照比空白好写
  if (props.nodeType === 'approval' && cfg.detail_template == null) {
    const trig = props.vars.find((g) => g.title === '触发器')
    const fields = (trig?.items || []).filter((it) => /^\{trigger\.record\.[a-zA-Z_]/.test(it.expr)).slice(0, 4)
    if (fields.length) {
      set('detail_template', fields.map((it) => `${it.label.replace('触发记录·', '')}：${it.expr}`).join('\n'))
    }
  }
  // HTTP 请求体模式：只在进入该节点时按已有 body 推断一次（嵌套结构 → JSON 模式，否则表单模式）。
  // 不能跟随编辑实时重算：JSON 模式下敲出合法扁平 JSON（如闭合 {}）会被误判而弹回表单模式
  if (props.nodeType === 'http_request' && !bodyModeInited) {
    bodyModeInited = true
    const b = cfg.body
    bodyMode.value = (b && typeof b === 'object' && Object.values(b).some((x) => x !== null && typeof x === 'object'))
      ? 'json' : 'form'
  }
  // 子流程传参：只在子流程选择变化时重新扫描（deep watch 每次击键都会触发，不能重复拉取）
  if (props.nodeType === 'sub_workflow' && cfg.workflow_id !== lastSubWfId) {
    lastSubWfId = cfg.workflow_id
    loadSubParams(cfg.workflow_id)
  }
}, { immediate: true, deep: true })

// 兜底表变化（如画布连线改动）且节点自身没选表时，重新加载字段
watch(() => props.fallbackTableId, (v) => {
  if (!cfg.table_id) loadFields(v)
})

// 邮件/短信接收人：标签数组 ⇄ 逗号分隔字符串（后端 _split_recipients 的存储格式）
const recipientsList = computed(() =>
  String(cfg.recipients || '').split(/[,，\n]/).map((s) => s.trim()).filter(Boolean))

function recipientRe(ch) {
  return ch === 'sms' ? /^[+\d][\d-]{4,}$/ : /^\S+@\S+\.\S+$/
}

function set(key, value) {
  cfg[key] = value
  if (key === 'table_id') loadFields(value || props.fallbackTableId)
  // 切换邮件/短信通道时清掉不适用于新通道的接收人：邮箱与手机号不通用，留着就是内容串通道
  if (key === 'channel' && props.nodeType === 'send_message' && cfg.recipients) {
    const re = recipientRe(value)
    const kept = recipientsList.value.filter((s) => re.test(s))
    const dropped = recipientsList.value.filter((s) => !re.test(s))
    if (dropped.length) {
      cfg.recipients = kept.join(',')
      ElMessage.warning(`已移除不适用于当前通道的接收人：${dropped.join('、')}`)
    }
  }
  emit('update:modelValue', { ...cfg })
}

function setRecipients(list) {
  // 逐个校验格式，不合格的拒收并提示（短信：纯数字/+/5 位以上；邮箱：基本形态）
  const re = recipientRe(cfg.channel)
  const bad = list.filter((s) => !re.test(s))
  if (bad.length) {
    ElMessage.warning(`已忽略格式不正确的${cfg.channel === 'sms' ? '手机号' : '邮箱'}：${bad.join('、')}`)
  }
  set('recipients', list.filter((s) => re.test(s)).join(','))
}
function setRules(v) {
  cfg.logic = v.logic
  cfg.rules = v.rules
  emit('update:modelValue', { ...cfg })
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
.preset-label { font-size: 12px; color: #909399; }
.preset-link { margin-right: 12px; }
.body-mode { margin-bottom: 6px; }
.ob-row { display: flex; align-items: center; gap: 6px; }
.ob-row .el-select, .ob-row .el-input { flex: 1; }
.ob-combo { display: flex; align-items: center; gap: 6px; }
.ob-combo .ob-field { flex: 1; min-width: 0; }
.hint-icon { margin-left: 4px; color: #c0c4cc; vertical-align: -2px; cursor: help; }
.schema-form :deep(.el-form-item) { margin-bottom: 14px; }
.schema-form :deep(.el-form-item__label) { padding-bottom: 2px !important; font-size: 12px; }
.field-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.field-hint.err { color: #f56c6c; }
.field-hint code { background: #f5f7fa; border: 1px solid #e4e7ed; border-radius: 4px; padding: 1px 5px; }
</style>
