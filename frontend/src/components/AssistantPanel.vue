<template>
  <!-- 全局 AI 助手：悬浮按钮 + 聊天抽屉 -->
  <el-button class="ai-fab" type="primary" circle size="large" :icon="ChatDotRound" @click="open" />
  <el-drawer v-model="visible" title="AI 助手" size="920px" destroy-on-close>
    <div class="chat-wrap">
      <div ref="listEl" class="msg-list">
        <div v-if="!messages.length" class="empty-hint">
          <p>试试这样问我：</p>
          <p class="hint-item" @click="quick('帮我向数据表插入一条数据')">「帮我向数据表插入一条数据」</p>
          <p class="hint-item" @click="quick('帮我建一个供应商台账数据表')">「帮我建一个供应商台账数据表」</p>
          <p class="hint-item" @click="quick('帮我创建一个数据表的销售周报')">「帮我创建一个数据表的销售周报」</p>
          <p class="hint-item" @click="quick('帮我创建一个超期未跟进提醒的任务规则')">「帮我创建一个超期未跟进提醒的任务规则」</p>
          <p class="hint-item" @click="quick('把数据表的数据导出 Excel')">「把数据表的数据导出 Excel」</p>
        </div>
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <div class="bubble">
            <div class="text">{{ m.content }}</div>

            <!-- 动作卡片：填记录 -->
            <div v-if="m.card?.type === 'fill_records'" class="card">
              <div class="card-title">📝 {{ m.card.summary }} → {{ m.card.table_label }}</div>
              <el-table :data="m.card.payload.records" size="small" border max-height="220">
                <el-table-column v-for="f in fillColumns(m.card)" :key="f" :label="fieldLabel(m.card, f)" min-width="90">
                  <template #default="{ row }">
                    <el-input v-model="row[f]" size="small" :disabled="!!m.done" />
                  </template>
                </el-table-column>
                <el-table-column v-if="!m.done" width="46" align="center">
                  <template #default="{ $index }">
                    <el-button text type="danger" size="small" @click="m.card.payload.records.splice($index, 1)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <warnings-view :list="m.card.warnings" />
              <card-footer :m="m" confirm-text="确认填入" @confirm="confirm(m)" />
            </div>

            <!-- 动作卡片：建表 -->
            <div v-else-if="m.card?.type === 'create_table'" class="card">
              <div class="card-title">🧱 {{ m.card.summary }}</div>
              <el-input v-model="m.card.payload.label" size="small" :disabled="!!m.done" style="margin-bottom: 6px" />
              <div v-for="(f, fi) in m.card.payload.fields" :key="fi" class="field-row">
                <el-input v-model="f.label" size="small" :disabled="!!m.done" style="width: 110px" />
                <el-select v-model="f.data_type" size="small" :disabled="!!m.done" style="width: 96px">
                  <el-option v-for="t in DATA_TYPES" :key="t" :label="t" :value="t" />
                </el-select>
                <el-checkbox v-model="f.nullable" size="small" :disabled="!!m.done">可空</el-checkbox>
                <el-button v-if="!m.done" text type="danger" size="small" @click="m.card.payload.fields.splice(fi, 1)">删</el-button>
              </div>
              <warnings-view :list="m.card.warnings" />
              <card-footer :m="m" confirm-text="确认建表" @confirm="confirm(m)" />
            </div>

            <!-- 动作卡片：创建报表 -->
            <div v-else-if="m.card?.type === 'create_report'" class="card">
              <div class="card-title">🧾 {{ m.card.summary }} → {{ m.card.table_label }}</div>
              <div class="kv-row">
                <span class="kv-k">名称</span>
                <el-input v-model="m.card.payload.name" size="small" :disabled="!!m.done" style="width: 220px" />
                <span class="kv-k" style="margin-left: 10px">口径</span>
                <span>{{ RANGE_LABELS[m.card.payload.range?.mode] || m.card.payload.range?.mode }}</span>
              </div>
              <div v-for="(b, bi) in m.card.payload.blocks" :key="bi" class="kv-row">
                <el-tag size="small" :type="BLOCK_TAG[b.type] || 'info'">{{ BLOCK_LABELS[b.type] || b.type }}</el-tag>
                <span style="margin-left: 6px">{{ b.title }}</span>
              </div>
              <warnings-view :list="m.card.warnings" />
              <card-footer :m="m" confirm-text="确认创建（默认不启用推送）" @confirm="confirm(m)" />
            </div>

            <!-- 动作卡片：创建任务规则 -->
            <div v-else-if="m.card?.type === 'create_task'" class="card">
              <div class="card-title">⏰ {{ m.card.summary }} → {{ m.card.table_label }}</div>
              <div class="kv-row">
                <span class="kv-k">名称</span>
                <el-input v-model="m.card.payload.name" size="small" :disabled="!!m.done" style="width: 220px" />
              </div>
              <div class="kv-row">
                <span class="kv-k">条件</span>
                <span>{{ taskConditionText(m.card.payload) }}</span>
              </div>
              <div class="kv-row">
                <span class="kv-k">周期</span>
                <span>{{ taskScheduleText(m.card.payload.schedule) }}</span>
              </div>
              <div class="kv-row">
                <span class="kv-k">动作</span>
                <span>{{ m.card.payload.action?.type }}：{{ (m.card.payload.action?.template || '').slice(0, 40) }}</span>
              </div>
              <warnings-view :list="m.card.warnings" />
              <card-footer :m="m" confirm-text="确认创建（默认停用）" @confirm="confirm(m)" />
            </div>

            <!-- 动作卡片：生成 Excel -->
            <div v-else-if="m.card?.type === 'gen_excel'" class="card">
              <div class="card-title">📊 {{ m.card.summary }}</div>
              <warnings-view :list="m.card.warnings" />
              <div v-if="m.download" class="done-text">
                ✅ 已生成
                <a :href="m.download.url" class="dl-link">{{ m.download.filename }}</a>
              </div>
              <card-footer v-else :m="m" confirm-text="确认生成" @confirm="confirm(m)" />
            </div>

            <!-- 动作卡片：数据问答（只读结果，无需确认） -->
            <div v-else-if="m.card?.type === 'query_answer'" class="card">
              <div class="card-title">🔍 {{ m.card.table_label }} · {{ m.card.result.range_label }}</div>
              <template v-if="m.card.result.type === 'stat'">
                <div class="answer-value">{{ m.card.result.value }}</div>
              </template>
              <template v-else-if="m.card.result.type === 'chart'">
                <el-table :data="chartRows(m.card.result)" size="small" border max-height="220">
                  <el-table-column label="分组" prop="label" min-width="90" />
                  <el-table-column v-for="s in m.card.result.series" :key="s.name" :label="s.name || '值'" :prop="s.name" align="right" min-width="80" />
                </el-table>
              </template>
              <template v-else-if="m.card.result.type === 'table'">
                <el-table :data="m.card.result.rows" size="small" border max-height="220">
                  <el-table-column v-for="c in m.card.result.columns" :key="c.prop" :prop="c.prop" :label="c.label" show-overflow-tooltip min-width="90" />
                </el-table>
                <div v-if="m.card.result.truncated" class="warn-line">共 {{ m.card.result.total }} 条，仅显示前 {{ m.card.result.rows.length }} 条</div>
              </template>
              <warnings-view :list="m.card.warnings" />
            </div>

            <!-- 动作卡片：联网搜索来源（只读，无需确认） -->
            <div v-else-if="m.card?.type === 'search_answer'" class="card">
              <div class="card-title">🌐 {{ m.card.summary }}</div>
              <div class="src-list">
                <a
                  v-for="(s, si) in m.card.payload.results" :key="si"
                  :href="s.url" target="_blank" rel="noopener" class="src-item"
                  :title="s.snippet"
                >{{ si + 1 }}. {{ s.title || s.url }}</a>
              </div>
            </div>

            <!-- 执行结果 -->
            <div v-if="m.done" class="done-text" v-html="m.done" />
            <div v-if="m.error" class="warn-line">{{ m.error }}</div>
          </div>
        </div>
        <div v-if="thinking" class="msg assistant"><div class="bubble text">AI 思考中…</div></div>
      </div>
      <div class="input-bar">
        <el-input
          v-model="draft" type="textarea" :rows="2" resize="none"
          placeholder="输入需求，Enter 发送（Shift+Enter 换行）"
          @keydown.enter.exact.prevent="send"
        />
        <div class="input-actions">
          <el-button text size="small" :disabled="!messages.length" @click="clear">清空对话</el-button>
          <el-button type="primary" size="small" :loading="thinking" :disabled="!draft.trim()" @click="send">发送</el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, h, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound } from '@element-plus/icons-vue'
import { assistantChat, assistantDownloadUrl, assistantExecute } from '../api'

const DATA_TYPES = ['varchar', 'text', 'int', 'decimal', 'date', 'datetime', 'bool']
const RANGE_LABELS = {
  today: '今天', yesterday: '昨天', past_7d: '近7天', past_30d: '近30天',
  this_week: '本周', last_week: '上周', this_month: '本月', last_month: '上月',
  this_quarter: '本季度', this_year: '今年', custom: '自定义',
}
const BLOCK_LABELS = { stat: '统计卡片', chart: '图表', pivot: '透视表', table: '明细表', text: '文本' }
const BLOCK_TAG = { stat: 'success', chart: 'primary', pivot: 'danger', table: 'warning', text: 'info' }

function taskConditionText(p) {
  if (p.condition_mode === 'llm') return `智能判断：${(p.condition?.description || '').slice(0, 50)}`
  return `结构化条件 ${p.condition?.rules?.length || 0} 条`
}

function taskScheduleText(s) {
  if (s?.type === 'interval') return `每隔 ${s.minutes} 分钟`
  if (s?.type === 'cron') return `cron：${s.expr}`
  return '未设置'
}

// 警告行内小组件（函数式，避免单文件组件嵌套）
const WarningsView = (props) =>
  (props.list || []).map((w) => h('div', { class: 'warn-line' }, `⚠ ${w}`))
WarningsView.props = { list: Array }

// 卡片底部：确认按钮 / 执行中 / 完成占位
const CardFooter = (props, { emit }) =>
  !props.m.done
    ? h('div', { class: 'card-actions' }, [
        h(
          'button',
          {
            class: 'confirm-btn',
            disabled: props.m.executing,
            onClick: () => emit('confirm'),
          },
          props.m.executing ? '执行中…' : props.confirmText,
        ),
      ])
    : null
CardFooter.props = { m: Object, confirmText: String }
CardFooter.emits = ['confirm']

const route = useRoute()
const router = useRouter()
const visible = ref(false)
const draft = ref('')
const thinking = ref(false)
const messages = ref([])
const listEl = ref(null)

const user = computed(() => JSON.parse(localStorage.getItem('grt_user') || 'null'))
const storageKey = computed(() => `grt_assistant_${user.value?.id || 'anon'}`)

// 当前页面上下文：表页带上 table_id，AI 默认往当前表填
const context = computed(() => {
  const m = route.path.match(/^\/t\/(\d+)/)
  if (m) return { page: 'table', table_id: Number(m[1]) }
  return { page: route.path }
})

function open() {
  visible.value = true
  if (!messages.value.length) loadHistory()
}

function loadHistory() {
  try {
    messages.value = JSON.parse(localStorage.getItem(storageKey.value) || '[]')
  } catch { messages.value = [] }
}

function saveHistory() {
  try {
    localStorage.setItem(storageKey.value, JSON.stringify(messages.value.slice(-50)))
  } catch { /* 存储满时静默 */ }
}

watch(messages, saveHistory, { deep: true })

function quick(text) {
  draft.value = text
  send()
}

function clear() {
  messages.value = []
}

async function scrollBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

// 历史消息的卡片摘要：让模型能看到自己之前查过什么、生成过什么预览（否则只有 reply 文本会"断片"）
function cardDigest(card) {
  if (!card) return ''
  try {
    if (card.type === 'search_answer') {
      const titles = (card.payload?.results || []).slice(0, 5).map((r) => r.title).filter(Boolean).join('；')
      return `[联网搜索：${(card.payload?.queries || []).join('、')}。来源：${titles}]`
    }
    if (card.type === 'fill_records') {
      const recs = (card.payload?.records || []).map((r) => JSON.stringify(r)).join('；')
      return `[填表预览 → ${card.table_label}：${recs}]`
    }
    if (card.type === 'create_table') {
      return `[建表预览：${card.payload?.label}（${(card.payload?.fields || []).map((f) => f.label).join('、')}）]`
    }
    if (card.type === 'create_report') return `[报表预览：${card.payload?.name}，${(card.payload?.blocks || []).length} 个区块]`
    if (card.type === 'create_task') return `[任务预览：${card.payload?.name}]`
    if (card.type === 'gen_excel') return `[生成 Excel：${card.summary}]`
    if (card.type === 'query_answer') {
      const r = card.result || {}
      const val = r.type === 'stat' ? r.value : r.type === 'chart' ? `分组 ${r.labels?.length} 项` : `清单 ${r.total} 条`
      return `[数据查询 ${card.table_label}（${r.range_label}）：${val}]`
    }
  } catch { /* 摘要失败不阻塞 */ }
  return ''
}

async function send() {
  const text = draft.value.trim()
  if (!text || thinking.value) return
  const history = messages.value.slice(-20).map((m) => {
    const digest = m.role === 'assistant' ? cardDigest(m.card) : ''
    return { role: m.role, content: digest ? `${m.content}\n${digest}` : m.content }
  })
  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  thinking.value = true
  scrollBottom()
  try {
    const res = await assistantChat({ message: text, history, context: context.value })
    messages.value.push({ role: 'assistant', content: res.reply || '（无回复）', card: res.action_card || null })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '', error: e.message })
  } finally {
    thinking.value = false
    scrollBottom()
  }
}

function fillColumns(card) {
  const keys = new Set()
  card.payload.records.forEach((r) => Object.keys(r).forEach((k) => keys.add(k)))
  const order = (card.payload.fields || []).map((f) => f.field_name)
  return [...keys].sort((a, b) => order.indexOf(a) - order.indexOf(b))
}

function fieldLabel(card, name) {
  return (card.payload.fields || []).find((f) => f.field_name === name)?.label || name
}

function chartRows(result) {
  const series = result.series?.length ? result.series : [{ name: '值', values: result.values }]
  return result.labels.map((l, i) => {
    const row = { label: l }
    series.forEach((s) => { row[s.name || '值'] = s.values[i] })
    return row
  })
}

const TYPE_DEFAULT_PAYLOAD = {
  fill_records: (card) => ({ table_id: card.table_id, records: card.payload.records }),
  create_table: (card) => card.payload,
  create_report: (card) => card.payload,
  create_task: (card) => card.payload,
  gen_excel: (card) => card.payload,
}

async function confirm(m) {
  if (m.executing || m.done) return
  m.executing = true
  try {
    const res = await assistantExecute({ type: m.card.type, payload: TYPE_DEFAULT_PAYLOAD[m.card.type](m.card) })
    if (res.type === 'fill_records') {
      let text = `✅ 已填入 ${res.ok} 条记录`
      if (res.fail?.length) text += `，失败 ${res.fail.length} 条（${res.fail[0].reason}）`
      text += ` · <a href="/t/${res.table_id}" class="dl-link">查看「${res.table_label}」</a>`
      m.done = text
    } else if (res.type === 'create_table') {
      m.done = `✅ 已创建「${res.table_label}」 · <a href="/t/${res.table_id}" class="dl-link">去使用</a>`
    } else if (res.type === 'create_report') {
      m.done = `✅ 已创建报表「${res.name}」 · <a href="/reports/${res.report_id}/view" class="dl-link">查看报表</a>`
    } else if (res.type === 'create_task') {
      m.done = `✅ 已创建任务「${res.name}」（默认停用，到任务规则页启用） · <a href="/tasks" class="dl-link">去查看</a>`
    } else if (res.type === 'gen_excel') {
      m.download = { url: assistantDownloadUrl(res.file_id), filename: res.filename }
    }
    ElMessage.success('执行完成')
  } catch (e) {
    m.error = e.message
  } finally {
    m.executing = false
    scrollBottom()
  }
}

// 路由变化时 context 自动更新；跨账号登录切换时重载历史
watch(storageKey, () => { messages.value = []; if (visible.value) loadHistory() })
</script>

<style scoped>
.ai-fab {
  position: fixed; right: 28px; bottom: 32px; z-index: 2000;
  width: 52px; height: 52px; box-shadow: 0 4px 12px rgba(64, 158, 255, .4);
}
.chat-wrap { display: flex; flex-direction: column; height: 100%; }
.msg-list { flex: 1; overflow-y: auto; padding: 4px 2px; }
.empty-hint { color: #909399; font-size: 13px; padding: 12px 6px; }
.hint-item { color: #409eff; cursor: pointer; margin: 8px 0; }
.msg { display: flex; margin-bottom: 12px; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 92%; background: #f5f7fa; border-radius: 10px; padding: 10px 12px;
  font-size: 14px; color: #303133;
}
.msg.user .bubble { background: #ecf5ff; }
.text { white-space: pre-wrap; word-break: break-word; }
.card { margin-top: 8px; border-top: 1px dashed #dcdfe6; padding-top: 8px; }
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.card-actions { margin-top: 8px; text-align: right; }
.confirm-btn {
  background: #409eff; color: #fff; border: none; border-radius: 6px;
  padding: 6px 16px; font-size: 13px; cursor: pointer;
}
.confirm-btn:disabled { background: #a0cfff; cursor: not-allowed; }
.field-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.kv-row { display: flex; align-items: center; font-size: 13px; margin-bottom: 6px; }
.kv-k { color: #909399; margin-right: 8px; flex-shrink: 0; }
.warn-line { font-size: 12px; color: #e6a23c; margin-top: 4px; }
.done-text { font-size: 13px; color: #67c23a; margin-top: 8px; }
.dl-link { color: #409eff; text-decoration: none; }
.answer-value { font-size: 28px; font-weight: 600; color: #303133; padding: 4px 0; }
.src-list { display: flex; flex-direction: column; gap: 4px; max-height: 180px; overflow-y: auto; }
.src-item {
  font-size: 12px; color: #409eff; text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.src-item:hover { text-decoration: underline; }
.input-bar { border-top: 1px solid #ebeef5; padding-top: 10px; }
.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
</style>
