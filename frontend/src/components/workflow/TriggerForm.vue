<template>
  <el-form label-position="top" size="small" class="trigger-form">
    <el-form-item label="触发方式">
      <el-select v-model="trigger.type" size="small" style="width: 100%">
        <el-option label="被动调用" value="manual" />
        <el-option label="定时触发" value="schedule" />
        <el-option label="记录新增时" value="record_created" />
        <el-option label="记录修改时" value="record_updated" />
        <el-option label="Webhook 回调" value="webhook" />
        <el-option label="表单提交（公开链接）" value="form" />
      </el-select>
      <div v-if="trigger.type === 'manual'" class="hint">
        不会自动触发：点「立即执行」/「试运行」、API/MCP 调用、被其他流程当子流程调用时运行（参数用 {trigger.params.xxx} 引用）
      </div>
    </el-form-item>

    <template v-if="trigger.type === 'schedule'">
      <el-form-item label="触发频率">
        <el-radio-group v-model="trigger.sched_kind" size="small">
          <el-radio-button value="interval">间隔</el-radio-button>
          <el-radio-button value="cron">Cron</el-radio-button>
        </el-radio-group>
        <div v-if="trigger.sched_kind === 'interval'" class="mt row">
          <span>每</span>
          <el-input-number v-model="trigger.minutes" :min="1" size="small" controls-position="right" style="width: 100px" />
          <span>分钟</span>
        </div>
        <!-- cron 可视化构建器：普通用户选频率+时间即可，「自定义」才暴露表达式 -->
        <template v-else>
          <div class="mt row">
            <el-select v-model="cronMode" size="small" style="width: 170px">
              <el-option label="每小时" value="hour" />
              <el-option label="每天" value="day" />
              <el-option label="每周" value="week" />
              <el-option label="每月" value="month" />
              <el-option label="自定义（cron 表达式）" value="custom" />
            </el-select>
            <template v-if="cronMode === 'hour'">
              <span>第</span>
              <el-input-number v-model="cronMinute" :min="0" :max="59" size="small" controls-position="right" style="width: 80px" />
              <span>分</span>
            </template>
            <template v-else-if="cronMode !== 'custom'">
              <el-select v-if="cronMode === 'week'" v-model="cronWeek" size="small" style="width: 90px">
                <el-option v-for="(w, i) in ['周一', '周二', '周三', '周四', '周五', '周六', '周日']" :key="i" :label="w" :value="i" />
              </el-select>
              <template v-if="cronMode === 'month'">
                <el-input-number v-model="cronDom" :min="1" :max="31" size="small" controls-position="right" style="width: 80px" />
                <span>日</span>
              </template>
              <el-time-picker v-model="cronTime" size="small" format="HH:mm" value-format="HH:mm"
                placeholder="时间" style="width: 110px" />
            </template>
          </div>
          <el-input v-if="cronMode === 'custom'" v-model="trigger.expr" size="small" class="mt"
            placeholder="cron 表达式：分 时 日 月 周（周一 = 0，周日 = 6）" />
          <div class="mt hint">实际生效：{{ trigger.expr }}</div>
        </template>
      </el-form-item>
    </template>

    <template v-if="trigger.type === 'record_created' || trigger.type === 'record_updated' || trigger.type === 'form'">
      <el-form-item :label="trigger.type === 'form' ? '表单写入的数据表' : '监听的数据表'">
        <el-select v-model="trigger.table_id" size="small" filterable style="width: 100%"
          placeholder="选择数据表" @change="$emit('table-change')">
          <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="trigger.type === 'record_updated'" label="监听字段">
        <el-select v-model="trigger.watch_fields" size="small" multiple style="width: 100%"
          placeholder="空 = 任意字段修改都触发">
          <el-option v-for="f in triggerFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
        </el-select>
      </el-form-item>
    </template>

    <template v-if="trigger.type === 'form'">
      <el-form-item label="公开表单链接">
        <template v-if="formUrl">
          <div class="hint mb">任何人打开此链接即可填表，提交后写入数据表并触发流程（保存并启用后生效）：</div>
          <el-input :model-value="formUrl" size="small" readonly>
            <template #append>
              <el-button @click="$emit('copy-form')">复制</el-button>
            </template>
          </el-input>
          <div class="mt">
            <el-button size="small" @click="openForm">打开表单预览</el-button>
          </div>
        </template>
        <div v-else class="hint">保存后自动生成公开表单链接（图片字段不会出现在表单里）</div>
      </el-form-item>
    </template>

    <template v-if="trigger.type === 'webhook'">
      <el-form-item label="回调地址">
        <template v-if="webhookUrl">
          <div class="hint mb">POST 此地址即触发（保存后生效）：</div>
          <el-input :model-value="webhookUrl" size="small" readonly>
            <template #append>
              <el-button @click="$emit('copy-webhook')">复制</el-button>
            </template>
          </el-input>
          <div class="mt">
            <el-button size="small" :loading="testing" @click="testWebhook">发测试请求</el-button>
          </div>
        </template>
        <div v-else class="hint">保存后自动生成 Webhook 回调地址</div>
      </el-form-item>
      <el-form-item label="自定义响应（可选）">
        <el-input v-model="trigger.response_template" type="textarea" :rows="3"
          placeholder='默认返回 {"ok": true}；验签场景可填 {"echostr": "{trigger.params.echostr}"}' />
        <div class="hint">支持 {trigger.params.xxx} 变量；内容是 JSON 则按 JSON 返回</div>
      </el-form-item>
    </template>

    <el-form-item label="工作流描述（可选）">
      <el-input :model-value="description" type="textarea" :rows="3" placeholder="这个流程是做什么的（会显示在工作流列表里）"
        @update:model-value="$emit('update:description', $event)" />
    </el-form-item>
  </el-form>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  trigger: { type: Object, required: true },      // 父组件的 reactive 触发器状态
  tables: { type: Array, default: () => [] },
  triggerFields: { type: Array, default: [] },
  webhookUrl: { type: String, default: '' },
  formUrl: { type: String, default: '' },
  description: { type: String, default: '' },
})
defineEmits(['update:description', 'table-change', 'copy-webhook', 'copy-form'])

// ---------- cron 可视化构建器 ----------
// 注意：调度器是 APScheduler（from_crontab），day_of_week 周一 = 0 … 周日 = 6（与 Unix cron 不同）
const cronMode = ref('day')
const cronMinute = ref(0)          // 每小时模式：第几分
const cronTime = ref('09:00')      // 天/周/月模式：HH:mm
const cronWeek = ref(0)            // 周一 = 0
const cronDom = ref(1)             // 每月几号

function parseCron(expr) {
  const p = (expr || '').trim().split(/\s+/)
  if (p.length !== 5) return 'custom'
  const [m, h, dom, , dow] = p
  const num = (s) => /^\d+$/.test(s)
  if (num(m) && h === '*' && dom === '*' && dow === '*') { cronMinute.value = Number(m); return 'hour' }
  if (num(m) && num(h) && dom === '*' && dow === '*') {
    cronTime.value = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`; return 'day'
  }
  if (num(m) && num(h) && dom === '*' && num(dow)) {
    cronTime.value = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`; cronWeek.value = Number(dow) % 7; return 'week'
  }
  if (num(m) && num(h) && num(dom) && dow === '*') {
    cronTime.value = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`; cronDom.value = Number(dom); return 'month'
  }
  return 'custom'
}

function buildCron() {
  const [h, m] = (cronTime.value || '09:00').split(':').map(Number)
  switch (cronMode.value) {
    case 'hour': return `${cronMinute.value} * * * *`
    case 'day': return `${m} ${h} * * *`
    case 'week': return `${m} ${h} * * ${cronWeek.value}`
    case 'month': return `${m} ${h} ${cronDom.value} * *`
    default: return props.trigger.expr
  }
}

// 构建器改动 → 写回表达式；外部载入（打开已有工作流）→ 反向解析回填构建器
watch([cronMode, cronMinute, cronTime, cronWeek, cronDom], () => {
  if (cronMode.value !== 'custom') props.trigger.expr = buildCron()
})
watch(() => props.trigger.expr, (expr) => {
  if (cronMode.value !== 'custom' && expr === buildCron()) return   // 自己写回的，不重复解析
  cronMode.value = parseCron(expr)
}, { immediate: true })

// ---------- Webhook 测试 / 表单预览 ----------
const testing = ref(false)

async function testWebhook() {
  testing.value = true
  try {
    const r = await fetch(props.webhookUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    })
    const data = await r.json().catch(() => null)
    if (r.ok) ElMessage.success(`触发成功，已投递执行（run_id: ${data?.run_id ?? '—'}），可在「执行日志」查看`)
    else ElMessage.error(`HTTP ${r.status}：请确认工作流已保存并处于启用状态`)
  } catch (e) {
    ElMessage.error(`请求失败：${e.message}`)
  } finally {
    testing.value = false
  }
}

function openForm() {
  window.open(props.formUrl, '_blank')
}
</script>

<style scoped>
.trigger-form :deep(.el-form-item) { margin-bottom: 14px; }
.trigger-form :deep(.el-form-item__label) { padding-bottom: 2px !important; font-size: 12px; }
.trigger-form :deep(.el-form-item__content) { display: block; }
.mt { margin-top: 8px; }
.mb { margin-bottom: 4px; }
.row { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #606266; }
.hint { font-size: 12px; color: #909399; }
</style>
