<template>
  <!-- 全局 AI 助手：悬浮按钮 + 聊天抽屉 -->
  <el-tooltip content="AI 助手" placement="left" :show-after="300">
    <button class="ai-fab" @click="open">✨</button>
  </el-tooltip>
  <el-drawer v-model="visible" size="min(920px, 94vw)" destroy-on-close>
    <template #header>
      <div class="ai-header">
        <span class="ai-header-icon">✨</span>
        <span class="ai-header-title">AI 助手</span>
        <span class="ai-header-sub">建表 · 填数 · 报表 · 提醒 · 问答</span>
      </div>
    </template>
    <div class="chat-wrap">
      <div ref="listEl" class="msg-list">
        <!-- 空状态：欢迎 + 建议问题卡片 -->
        <div v-if="!messages.length" class="empty">
          <div class="empty-logo">✨</div>
          <div class="empty-title">我是你的 AI 助手</div>
          <div class="empty-sub">可以帮你建数据表、填记录、做报表、设提醒，也可以直接问数据</div>
          <div class="suggest-grid">
            <div v-for="s in SUGGESTIONS" :key="s.label" class="suggest-card" @click="quick(s.text)">
              <span class="suggest-icon">{{ s.icon }}</span>
              <span class="suggest-text">{{ s.label }}</span>
            </div>
          </div>
        </div>

        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <div v-if="m.role !== 'user'" class="avatar avatar-ai">🤖</div>
          <div class="msg-main">
            <div class="bubble">
              <div v-if="m.images?.length" class="msg-images">
                <img v-for="(img, ii) in m.images" :key="ii" :src="img" class="msg-img" alt="附图" />
              </div>
              <div v-if="m.content" class="text" v-html="renderText(m.content)" />

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
              <div v-if="m.error" class="error-line">❌ {{ m.error }}</div>
            </div>
            <div v-if="m.ts" class="msg-time">{{ fmtTime(m.ts) }}</div>
          </div>
          <div v-if="m.role === 'user'" class="avatar avatar-user">{{ userInitial }}</div>
        </div>

        <!-- 思考中 -->
        <div v-if="thinking" class="msg assistant">
          <div class="avatar avatar-ai">🤖</div>
          <div class="msg-main">
            <div class="bubble thinking-bubble">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </div>
          </div>
        </div>
      </div>

      <div class="input-bar">
        <div v-if="attachments.length" class="attach-strip">
          <div v-for="(a, i) in attachments" :key="i" class="attach-item">
            <img :src="a" class="attach-img" alt="待发送图片" />
            <span class="attach-del" @click="attachments.splice(i, 1)">✕</span>
          </div>
        </div>
        <el-input
          v-model="draft" type="textarea" :rows="2" resize="none" class="input-box"
          placeholder="输入需求，Enter 发送（Shift+Enter 换行），可直接粘贴截图"
          @keydown.enter.exact.prevent="send"
          @paste="onPaste"
        />
        <div class="input-actions">
          <el-button text :icon="CirclePlus" :disabled="!messages.length" class="new-session-btn" @click="newSession">新建会话</el-button>
          <el-button
            type="primary" circle size="large" :icon="Promotion"
            :loading="thinking" :disabled="!draft.trim() && !attachments.length" class="send-btn" @click="send"
          />
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, h, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Promotion, CirclePlus } from '@element-plus/icons-vue'
import { assistantChat, assistantDownloadUrl, assistantExecute } from '../api'

const DATA_TYPES = ['varchar', 'text', 'int', 'decimal', 'date', 'datetime', 'bool']
const RANGE_LABELS = {
  today: '今天', yesterday: '昨天', past_7d: '近7天', past_30d: '近30天',
  this_week: '本周', last_week: '上周', this_month: '本月', last_month: '上月',
  this_quarter: '本季度', this_year: '今年', custom: '自定义',
}
const BLOCK_LABELS = { stat: '统计卡片', chart: '图表', pivot: '透视表', table: '明细表', text: '文本' }
const BLOCK_TAG = { stat: 'success', chart: 'primary', pivot: 'danger', table: 'warning', text: 'info' }

const SUGGESTIONS = [
  { icon: '📝', label: '插入一条数据', text: '帮我向数据表插入一条数据' },
  // 建表/报表/提醒故意不指定对象：让 AI 追问需求或目标表，而不是替用户编造
  { icon: '🧱', label: '创建数据表', text: '我想创建一个数据表' },
  { icon: '📊', label: '做一份报表', text: '我想做一份数据报表' },
  { icon: '⏰', label: '创建提醒任务', text: '我想创建一个提醒任务' },
  { icon: '📤', label: '导出 Excel', text: '把数据表的数据导出 Excel' },
]

function taskConditionText(p) {
  if (p.condition_mode === 'llm') return `智能判断：${(p.condition?.description || '').slice(0, 50)}`
  return `结构化条件 ${p.condition?.rules?.length || 0} 条`
}

function taskScheduleText(s) {
  if (s?.type === 'interval') return `每隔 ${s.minutes} 分钟`
  if (s?.type === 'cron') return `cron：${s.expr}`
  return '未设置'
}

// 轻量 Markdown：先转义 HTML，再支持 **加粗**、`行内代码`、- 列表（不引入三方库）
function renderText(text) {
  let html = (text || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  html = html.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/^\s*[-•]\s+/gm, '<span class="li-dot">•</span> ')
  return html
}

function fmtTime(ts) {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return sameDay ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`
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
const attachments = ref([])   // 待发送图片（JPEG data URL，已压缩）
const listEl = ref(null)

const user = computed(() => JSON.parse(localStorage.getItem('grt_user') || 'null'))
const storageKey = computed(() => `grt_assistant_${user.value?.id || 'anon'}`)
const userInitial = computed(() => (user.value?.username || '我').slice(0, 1).toUpperCase())

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
    // 图片 data URL 体积大，不入库；保留 imageCount 供历史摘要使用
    const slim = messages.value.slice(-50).map((m) => ({ ...m, images: undefined }))
    localStorage.setItem(storageKey.value, JSON.stringify(slim))
  } catch { /* 存储满时静默 */ }
}

watch(messages, saveHistory, { deep: true })

function quick(text) {
  draft.value = text
  send()
}

// 新建会话：清空消息与未发送草稿，回到引导页（历史随 localStorage 一并清掉）
function newSession() {
  messages.value = []
  draft.value = ''
  attachments.value = []
}

// 粘贴的图片统一压缩为 JPEG（最长边 1600），兼顾识别清晰度与上传体积
function fileToJpeg(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片读取失败')) }
    img.src = url
  })
}

async function onPaste(e) {
  const items = [...(e.clipboardData?.items || [])]
  const files = items.filter((it) => it.kind === 'file' && it.type.startsWith('image/')).map((it) => it.getAsFile())
  if (!files.length) return
  e.preventDefault()
  for (const f of files) {
    if (attachments.value.length >= 4) {
      ElMessage.warning('最多附 4 张图片')
      break
    }
    try {
      attachments.value.push(await fileToJpeg(f))
    } catch {
      ElMessage.error('图片读取失败')
    }
  }
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
  if ((!text && !attachments.value.length) || thinking.value) return
  const images = attachments.value.slice()
  const history = messages.value.slice(-20).map((m) => {
    if (m.role === 'user') {
      const n = m.imageCount || m.images?.length || 0
      return { role: m.role, content: n ? `${m.content}\n[用户附了 ${n} 张图片]` : m.content }
    }
    const digest = cardDigest(m.card)
    return { role: m.role, content: digest ? `${m.content}\n${digest}` : m.content }
  })
  messages.value.push({ role: 'user', content: text, images, imageCount: images.length, ts: Date.now() })
  draft.value = ''
  attachments.value = []
  thinking.value = true
  scrollBottom()
  try {
    const res = await assistantChat({ message: text, history, context: context.value, images })
    messages.value.push({ role: 'assistant', content: res.reply || '（无回复）', card: res.action_card || null, ts: Date.now() })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '', error: e.message, ts: Date.now() })
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
/* 悬浮入口 */
.ai-fab {
  position: fixed; right: 28px; bottom: 32px; z-index: 2000;
  width: 52px; height: 52px; border-radius: 50%; border: none; cursor: pointer;
  font-size: 22px; line-height: 1;
  background: linear-gradient(135deg, #409eff, #7b5cff);
  box-shadow: 0 6px 16px rgba(80, 110, 255, .45);
  transition: transform .2s ease, box-shadow .2s ease;
}
.ai-fab:hover { transform: translateY(-3px) scale(1.05); box-shadow: 0 10px 22px rgba(80, 110, 255, .5); }

/* 抽屉头 */
.ai-header { display: flex; align-items: center; gap: 10px; }
.ai-header-icon {
  width: 32px; height: 32px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #ecf5ff, #f0e9ff); font-size: 16px;
}
.ai-header-title { font-size: 16px; font-weight: 600; color: #303133; }
.ai-header-sub { font-size: 12px; color: #909399; }

.chat-wrap { display: flex; flex-direction: column; height: 100%; }
.msg-list { flex: 1; overflow-y: auto; padding: 4px 2px; }
.msg-list::-webkit-scrollbar { width: 6px; }
.msg-list::-webkit-scrollbar-thumb { background: #dcdfe6; border-radius: 3px; }

/* 空状态 */
.empty { padding: 40px 16px 16px; text-align: center; }
.empty-logo {
  width: 64px; height: 64px; margin: 0 auto; border-radius: 20px; font-size: 30px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #ecf5ff, #f0e9ff);
}
.empty-title { font-size: 18px; font-weight: 600; color: #303133; margin-top: 14px; }
.empty-sub { font-size: 13px; color: #909399; margin-top: 6px; }
.suggest-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px; margin-top: 22px; text-align: left;
}
.suggest-card {
  display: flex; align-items: center; gap: 10px; padding: 12px 14px; cursor: pointer;
  background: #fff; border: 1px solid #ebeef5; border-radius: 10px;
  font-size: 13px; color: #606266;
  transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease;
}
.suggest-card:hover {
  border-color: #409eff; box-shadow: 0 4px 12px rgba(64, 158, 255, .12); transform: translateY(-1px);
}
.suggest-icon { font-size: 18px; }

/* 消息 */
.msg { display: flex; margin-bottom: 16px; gap: 8px; animation: msg-in .25s ease; }
@keyframes msg-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.msg.user { justify-content: flex-end; }
.avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 15px;
}
.avatar-ai { background: linear-gradient(135deg, #ecf5ff, #f0e9ff); }
.avatar-user {
  background: linear-gradient(135deg, #409eff, #7b5cff);
  color: #fff; font-size: 13px; font-weight: 600;
}
.msg-main { max-width: 86%; display: flex; flex-direction: column; }
.msg.user .msg-main { align-items: flex-end; }
.bubble {
  background: #fff; border: 1px solid #ebeef5; border-radius: 4px 14px 14px 14px;
  padding: 10px 14px; font-size: 14px; color: #303133;
  box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}
.msg.user .bubble {
  background: linear-gradient(135deg, #409eff, #5b8cff);
  border: none; border-radius: 14px 4px 14px 14px; color: #fff;
}
.msg-time { font-size: 11px; color: #c0c4cc; margin-top: 4px; }
.text { white-space: pre-wrap; word-break: break-word; line-height: 1.7; }
.text :deep(.inline-code) {
  background: #f2f6fc; border-radius: 4px; padding: 1px 5px;
  font-family: Consolas, monospace; font-size: 13px; color: #d63384;
}
.msg.user .text :deep(.inline-code) { background: rgba(255, 255, 255, .2); color: #fff; }
.text :deep(.li-dot) { color: #409eff; margin-right: 2px; }

/* 思考中三点动画 */
.thinking-bubble { display: flex; gap: 5px; padding: 14px 16px; }
.dot {
  width: 7px; height: 7px; border-radius: 50%; background: #a0cfff;
  animation: dot-bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: .15s; }
.dot:nth-child(3) { animation-delay: .3s; }
@keyframes dot-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: .5; }
  30% { transform: translateY(-5px); opacity: 1; }
}

/* 动作卡片 */
.card { margin-top: 8px; border-top: 1px dashed #dcdfe6; padding-top: 8px; }
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.card-actions { margin-top: 8px; text-align: right; }
.confirm-btn {
  background: linear-gradient(135deg, #409eff, #5b8cff); color: #fff; border: none; border-radius: 6px;
  padding: 6px 16px; font-size: 13px; cursor: pointer;
  transition: filter .15s ease;
}
.confirm-btn:hover { filter: brightness(1.08); }
.confirm-btn:disabled { background: #a0cfff; cursor: not-allowed; }
.field-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.kv-row { display: flex; align-items: center; font-size: 13px; margin-bottom: 6px; }
.kv-k { color: #909399; margin-right: 8px; flex-shrink: 0; }
.warn-line { font-size: 12px; color: #e6a23c; margin-top: 4px; }
.error-line {
  font-size: 12px; color: #f56c6c; margin-top: 6px;
  background: #fef0f0; border-radius: 6px; padding: 6px 10px;
}
.done-text { font-size: 13px; color: #67c23a; margin-top: 8px; }
.dl-link { color: #409eff; text-decoration: none; }
.answer-value { font-size: 28px; font-weight: 600; color: #303133; padding: 4px 0; }
.src-list { display: flex; flex-direction: column; gap: 4px; max-height: 180px; overflow-y: auto; }
.src-item {
  font-size: 12px; color: #409eff; text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.src-item:hover { text-decoration: underline; }

/* 输入区 */
.input-bar { border-top: 1px solid #ebeef5; padding-top: 12px; }
.attach-strip { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.attach-item { position: relative; width: 64px; height: 64px; }
.attach-img {
  width: 64px; height: 64px; object-fit: cover; border-radius: 8px; border: 1px solid #ebeef5;
}
.attach-del {
  position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%;
  background: rgba(0, 0, 0, .55); color: #fff; font-size: 11px; line-height: 18px; text-align: center;
  cursor: pointer;
}
.attach-del:hover { background: rgba(0, 0, 0, .75); }
.msg-images { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.msg-img {
  max-width: 200px; max-height: 140px; border-radius: 8px; object-fit: cover;
  background: rgba(255, 255, 255, .25);
}
.input-box :deep(.el-textarea__inner) {
  border-radius: 12px; padding: 10px 12px; box-shadow: 0 0 0 1px #dcdfe6 inset;
  transition: box-shadow .15s ease;
}
.input-box :deep(.el-textarea__inner:focus) { box-shadow: 0 0 0 1px #409eff inset; }
.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.new-session-btn { font-size: 14px; }
.send-btn {
  background: linear-gradient(135deg, #409eff, #7b5cff); border: none;
  box-shadow: 0 4px 10px rgba(80, 110, 255, .35);
}
.send-btn:disabled { background: #a0cfff; box-shadow: none; }
</style>
