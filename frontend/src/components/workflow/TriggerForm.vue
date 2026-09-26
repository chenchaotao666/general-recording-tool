<template>
  <div class="trigger-form">
    <el-select v-model="trigger.type" size="small" style="width: 100%">
      <el-option label="被动调用" value="manual" />
      <el-option label="定时触发" value="schedule" />
      <el-option label="记录新增时" value="record_created" />
      <el-option label="记录修改时" value="record_updated" />
      <el-option label="Webhook 回调" value="webhook" />
      <el-option label="表单提交（公开链接）" value="form" />
    </el-select>
    <div v-if="trigger.type === 'manual'" class="mt hint">
      不会自动触发：点「立即执行」/「试运行」、API/MCP 调用、被其他流程当子流程调用时运行（参数用 {trigger.params.xxx} 引用）
    </div>

    <template v-if="trigger.type === 'schedule'">
      <el-radio-group v-model="trigger.sched_kind" size="small" class="mt">
        <el-radio-button value="interval">间隔</el-radio-button>
        <el-radio-button value="cron">Cron</el-radio-button>
      </el-radio-group>
      <div v-if="trigger.sched_kind === 'interval'" class="mt row">
        <span>每</span>
        <el-input-number v-model="trigger.minutes" :min="1" size="small" controls-position="right" style="width: 100px" />
        <span>分钟</span>
      </div>
      <el-select v-else v-model="trigger.expr" size="small" filterable allow-create class="mt" placeholder="cron 表达式">
        <el-option label="每小时" value="0 * * * *" />
        <el-option label="每天 9:00" value="0 9 * * *" />
        <el-option label="每天 18:00" value="0 18 * * *" />
        <el-option label="每周一 9:00" value="0 9 * * 1" />
      </el-select>
    </template>

    <template v-if="trigger.type === 'record_created' || trigger.type === 'record_updated' || trigger.type === 'form'">
      <el-select v-model="trigger.table_id" size="small" filterable class="mt"
        :placeholder="trigger.type === 'form' ? '表单写入的数据表' : '监听的数据表'"
        @change="$emit('table-change')">
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <el-select v-if="trigger.type === 'record_updated'" v-model="trigger.watch_fields" size="small" multiple
        class="mt" placeholder="监听字段（空 = 任意修改）">
        <el-option v-for="f in triggerFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
      </el-select>
    </template>

    <template v-if="trigger.type === 'form'">
      <div v-if="formUrl" class="mt webhook-url">
        <div class="hint">任何人打开此链接即可填表，提交后写入数据表并触发流程（保存并启用后生效）：</div>
        <el-input :model-value="formUrl" size="small" readonly>
          <template #append>
            <el-button @click="$emit('copy-form')">复制</el-button>
          </template>
        </el-input>
      </div>
      <div v-else class="mt hint">保存后自动生成公开表单链接（图片字段不会出现在表单里）</div>
    </template>

    <template v-if="trigger.type === 'webhook'">
      <div v-if="webhookUrl" class="mt webhook-url">
        <div class="hint">POST 此地址即触发（保存后生效）：</div>
        <el-input :model-value="webhookUrl" size="small" readonly>
          <template #append>
            <el-button @click="$emit('copy-webhook')">复制</el-button>
          </template>
        </el-input>
      </div>
      <div v-else class="mt hint">保存后自动生成 Webhook 回调地址</div>
      <el-input v-model="trigger.response_template" type="textarea" :rows="3" class="mt"
        placeholder='自定义响应（可选）：默认返回 {"ok": true}；验签场景可填 {"echostr": "{trigger.params.echostr}"}' />
      <div class="mt hint">支持 {trigger.params.xxx} 变量；内容是 JSON 则按 JSON 返回</div>
    </template>

    <el-input :model-value="description" type="textarea" :rows="3" class="mt" placeholder="描述（可选）"
      @update:model-value="$emit('update:description', $event)" />
  </div>
</template>

<script setup>
defineProps({
  trigger: { type: Object, required: true },      // 父组件的 reactive 触发器状态
  tables: { type: Array, default: () => [] },
  triggerFields: { type: Array, default: () => [] },
  webhookUrl: { type: String, default: '' },
  formUrl: { type: String, default: '' },
  description: { type: String, default: '' },
})
defineEmits(['update:description', 'table-change', 'copy-webhook', 'copy-form'])
</script>

<style scoped>
.mt { margin-top: 8px; }
.row { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #606266; }
.hint { font-size: 12px; color: #909399; }
.webhook-url .hint { margin-bottom: 4px; }
</style>
