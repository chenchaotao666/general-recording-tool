<template>
  <!-- 节点说明：由节点目录的 description/config_schema/output_schema 自动生成，
       输出变量的路径示例直接用当前节点 id（可复制），EXTRA 只补 schema 表达不了的坑 -->
  <el-dialog :model-value="modelValue" :title="`${nt?.name || ''} · 节点说明`" width="540px"
    @update:model-value="$emit('update:modelValue', $event)">
    <div class="doc-sec">
      <div class="doc-h">功能</div>
      <p class="doc-p">{{ nt?.description || '（暂无说明）' }}</p>
    </div>

    <div v-if="inputs.length" class="doc-sec">
      <div class="doc-h">输入（配置项）</div>
      <div v-for="p in inputs" :key="p.key" class="doc-row">
        <span class="doc-k">{{ p.title }}<span v-if="p.required" class="req"> *</span></span>
        <span class="doc-v">{{ p.desc || '—' }}</span>
      </div>
    </div>

    <div v-if="outputs.length" class="doc-sec">
      <div class="doc-h">输出（下游节点可引用，点击复制）</div>
      <div v-for="o in outputs" :key="o.key" class="doc-row">
        <span class="doc-k">{{ o.key }}</span>
        <span class="doc-v">
          <code class="expr" title="点击复制" @click="copy(o.expr)">{{ o.expr }}</code>
          <div v-if="o.isArray" class="doc-note">列表：通知里用 <code class="expr" @click="copy(o.tableExpr)">{{ o.tableExpr }}</code> 渲染成表格，或 <code class="expr" @click="copy(o.listExpr)">{{ o.listExpr }}</code> 编号清单</div>
        </span>
      </div>
    </div>

    <div v-if="extra.tips?.length" class="doc-sec">
      <div class="doc-h">使用提示</div>
      <div v-for="(t, i) in extra.tips" :key="i" class="doc-tip">💡 {{ t }}</div>
    </div>

    <div v-if="extra.errors?.length" class="doc-sec">
      <div class="doc-h">常见报错</div>
      <div v-for="([msg, fix], i) in extra.errors" :key="i" class="doc-err">
        <div class="err-msg">✗ {{ msg }}</div>
        <div class="err-fix">→ {{ fix }}</div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  nt: { type: Object, default: null },        // 节点目录项（含 config_schema/output_schema/description）
  nodeId: { type: String, default: '' },       // 当前节点 id：输出变量示例直接可用
  config: { type: Object, default: () => ({}) }, // 当前节点配置：动态输出键（统计项/JSON 键名）从这里展开
})
defineEmits(['update:modelValue'])

// schema 表达不了的接法/坑，按节点类型补充（保持克制，只写真正高频的困惑）
const EXTRA = {
  foreach: {
    tips: [
      '接线：「每条」出口接循环体，循环体末尾用普通边连回本节点（回边）；「完成」出口接后续节点',
      '循环体里用 {nodes.本节点.item.字段名} 引用当前条目；「最多处理条数」可勾不限制，列表很长时先用上游查询收窄（引擎有单 Run 1000 步总量兜底）',
    ],
    errors: [['记录列表收到的是文本/对象', 'items 必须填整体引用，如 {nodes.q_1.records}，不能手输字段名']],
  },
  send_message: {
    errors: [
      ['没有可用的收件人/手机号', '检查接收人格式：邮箱需含 @，短信为手机号；多个收件人逐个回车添加'],
      ['未配置短信网关', '到「设置 → 通知渠道」配置短信 URL 模板（{phone}/{content} 占位）'],
      ['机器人返回异常 / errcode 非 0', '钉钉机器人若开了「自定义关键词」安全设置，消息里必须包含该词'],
    ],
  },
  approval: {
    tips: ['执行到审批会暂停（waiting），审批人收站内通知，点免登链接通过后流程继续；下游可判断 {nodes.本节点.approved}'],
  },
  delay: { tips: ['延迟到期自动恢复执行，无需人工干预；试运行时只模拟不真实等待'] },
  sub_workflow: {
    tips: ['子流程的触发方式必须是「被动调用」；子流程里用 {trigger.params.键} 接收父流程传参'],
    errors: [['检测到循环调用', '子流程不能直接或间接调用自己（嵌套最多 3 层）']],
  },
  http_request: {
    errors: [['目标域名不在白名单 / 请求被拒绝', '内网地址默认禁止；到「设置 → 通知渠道」的 workflow_http.allow_domains 加白'],
    ],
  },
  llm_transform: {
    tips: ['文本输出下游用 {nodes.本节点.text}；JSON 输出先填「JSON 输出键名」，下游用 {nodes.本节点.data.键名}'],
  },
  aggregate: {
    tips: [
      '统计结果按「统计项显示名」取数：{nodes.本节点.stats.总金额}（没填显示名则自动用 sum_amount 这种形式）',
      '配了分组字段时，groups 是数组：每项 {key: 分组值, 统计项显示名: 值}，可接「记录列表（表格）」渲染或逐条处理',
    ],
  },
}

const extra = computed(() => EXTRA[props.nt?.type] || {})

const requiredKeys = computed(() => props.nt?.config_schema?.required || [])
const inputs = computed(() =>
  Object.entries(props.nt?.config_schema?.properties || {}).map(([key, spec]) => ({
    key,
    title: spec.title || key,
    desc: spec.description || '',
    required: requiredKeys.value.includes(key),
  }))
)

// 动态输出键：schema 只能声明容器（stats 对象/data 对象），真正的键来自用户配置，按当前节点展开
const dynamicOutputs = computed(() => {
  const id = props.nodeId
  if (props.nt?.type === 'aggregate') {
    return (props.config?.aggs || [])
      .filter((a) => a && typeof a === 'object')
      .map((a) => {
        // 与后端 _run_aggs 的键规则一致：显示名优先，否则 op_field
        const key = String(a.title || '').trim() || (a.field ? `${a.op}_${a.field}` : a.op)
        return { key: `stats.${key}`, expr: `{nodes.${id}.stats.${key}}`, isArray: false }
      })
  }
  if (props.nt?.type === 'llm_transform' && (props.config?.output_format || 'text') === 'json') {
    return (props.config?.output_keys || [])
      .filter((k) => typeof k === 'string' && k.trim())
      .map((k) => ({ key: `data.${k.trim()}`, expr: `{nodes.${id}.data.${k.trim()}}`, isArray: false }))
  }
  return []
})

const outputs = computed(() => [
  ...Object.entries(props.nt?.output_schema?.properties || {}).map(([key, spec]) => {
    const base = `nodes.${props.nodeId}.${key}`
    return {
      key,
      isArray: spec.type === 'array',
      expr: `{${base}}`,
      tableExpr: `{${base} | 表格}`,
      listExpr: `{${base} | 列表}`,
    }
  }),
  ...dynamicOutputs.value,
])

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(`已复制 ${text}`)
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}
</script>

<style scoped>
.doc-sec { margin-bottom: 16px; }
.doc-h { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 6px; padding-left: 8px; border-left: 3px solid #409eff; }
.doc-p { margin: 0; font-size: 13px; color: #606266; line-height: 1.7; }
.doc-row { display: flex; gap: 10px; font-size: 12px; padding: 4px 0; }
.doc-k { width: 130px; flex-shrink: 0; color: #303133; font-weight: 500; }
.doc-v { flex: 1; color: #909399; line-height: 1.6; }
.req { color: #f56c6c; }
.expr {
  background: #f5f7fa; border: 1px solid #e4e7ed; border-radius: 4px; padding: 1px 6px;
  font-size: 12px; color: #409eff; cursor: pointer; word-break: break-all;
}
.expr:hover { background: #ecf5ff; }
.doc-note { margin-top: 3px; font-size: 12px; }
.doc-tip { font-size: 12px; color: #606266; line-height: 1.8; }
.doc-err { margin-bottom: 6px; }
.err-msg { font-size: 12px; color: #f56c6c; }
.err-fix { font-size: 12px; color: #909399; margin-top: 1px; }
</style>
