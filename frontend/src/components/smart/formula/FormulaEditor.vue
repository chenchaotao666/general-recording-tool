<template>
  <!-- 公式编辑器（设计文档 §9.1）：
       上（紧凑）：标题 + 格式优化 / 💡AI / ✕ → 公式输入框（字段胶囊，自适应高度）→ 运算符快捷条 →「第 1 行 = 结果 / 错误诊断」+ 确定
       下（主体）：当前函数签名条 → 三栏：字段（搜索 + 第 1 行取值）｜ 函数（搜索 + 分类）｜ 说明（签名 / 示例，可一键插入）
       输入框内打字时在光标处弹出联想（函数 + 字段），↑↓ 选择，Tab / ⏎ 插入 -->
  <teleport to="body">
    <div v-if="visible" ref="layerRef" class="fxe-mask" @click.self="emit('close')">
      <div ref="panelRef" v-panel-drag="{ handle: '.fxe-head' }" class="fxe">
        <div class="fxe-top">
          <div class="fxe-head">
            <span class="fxe-title">{{ title || '公式' }}</span>
            <button type="button" class="fxe-tool" @click="format"><StIcon name="brush" :size="15" />格式优化</button>
            <span class="fxe-vsep" />
            <el-tooltip :hide-after="0" content="用一句话描述，AI 帮你写公式" placement="bottom">
              <button type="button" class="fxe-tool"  :class="{ active: aiVisible }" :aria-pressed="aiVisible" @click="aiVisible = !aiVisible"><StIcon name="bulb" :size="16" />AI 写公式</button>
            </el-tooltip>
            <button type="button" aria-label="关闭公式编辑器" class="fxe-ico st-icon-action" @click="emit('close')"><StIcon name="close" :size="18" /></button>
          </div>
          <div ref="editorRef" class="fxe-editor st-field-rich-editor" contenteditable="true" spellcheck="false"
               data-placeholder="从下方点选字段和函数，或直接输入，如 IF([状态]=&quot;完成&quot;, 1, 0)"
               @focus="fieldTarget = 'formula'" @input="onInput" @keydown="onKeydown" @keyup="onKeyup" @mousedown="onEditorMouseDown" @mouseup="onCaretMove" @blur="onBlur"
               @paste="onPaste" />
          <div class="fxe-ops">
            <button type="button" v-for="op in OPS" :key="op.v" class="fxe-op" :data-smart-tip="op.tip" :aria-label="op.tip" @mousedown.prevent @click="insertText(op.v, op.back)">{{ op.label }}</button>
            <span class="fxe-ops-hint">输入字母或字段名可联想，Tab 补全</span>
          </div>
          <div class="fxe-result">
            <div class="fxe-res-main">
              <template v-if="!srcText.trim()"><span class="fxe-res-dim">输入公式后，这里会用第 1 行数据实时试算</span></template>
              <template v-else-if="preview.loading && !result"><span class="fxe-res-dim">计算中…</span></template>
              <template v-else-if="result?.empty"><span class="fxe-res-dim">表中暂无记录，保存后将自动计算</span></template>
              <template v-else-if="result && !result.ok">
                <span v-if="result.row_no && !result.blocking" class="fxe-res-label">第 {{ result.row_no }} 行 =</span>
                <div><div class="fxe-err-t">{{ result.error.title }}</div><div class="fxe-err-m">{{ result.error.message }}</div></div>
              </template>
              <template v-else-if="result && !result.blank">
                <span class="fxe-res-label">第 {{ result.row_no }} 行 =</span>
                <span class="fxe-res-val">{{ result.display === '' ? '（空）' : result.display }}</span>
              </template>
            </div>
            <el-button type="primary" class="st-button st-button--primary fxe-ok" :disabled="!canSave" @click="save">确定</el-button>
          </div>
        </div>

        <div v-if="sigView" class="fxe-sig">
          <template v-if="sigView">
            <span v-if="sigView.prefix" class="fxe-sig-dim">{{ sigView.prefix }}.</span>{{ sigView.head }}<template
              v-for="(a, i) in sigView.args" :key="i"><span :class="{ 'fxe-sig-cur': i === sigView.cur }">{{ a }}</span><span
              v-if="i < sigView.args.length - 1">, </span></template>{{ sigView.tail }}
          </template>
        </div>

        <div class="fxe-panes">
          <!-- 字段：本表字段 | 整表引用 -->
          <div class="fxe-col fxe-col-fields">
            <div class="fxe-col-head">
              <span>表字段</span>
              <span class="fxe-col-sub">第 {{ result?.row_no || 1 }} 行取值</span>
            </div>
            <el-input v-model="fieldKw" size="small" placeholder="搜索字段" clearable class="st-control st-control--small fxe-search" />
            <div class="fxe-col-list">
              <div v-for="f in fieldList" :key="f.field_name" class="fxe-item" :class="{ on: hover?.key === `f:${f.field_name}` }"
                   @mouseenter="hover = fieldItem(f)" @mousedown.prevent @click="insertSelectedField(f)">
                <StIcon :name="fieldIconName(f)" :size="14" class="fxe-item-ico" />
                <span class="fxe-item-name">{{ f.label }}</span>
                <span class="fxe-item-val">{{ rowValues[f.field_name] || '' }}</span>
              </div>
              <div v-if="!fieldList.length" class="fxe-none">没有匹配的字段</div>
            </div>
          </div>
          <!-- 函数 -->
          <div class="fxe-col fxe-col-funcs">
            <div class="fxe-col-head">函数</div>
            <div v-if="catalogError" class="fxe-none">函数加载失败，<button class="st-button" @click="loadCatalog">重新加载</button></div>
            <el-input v-model="fnKw" size="small" placeholder="搜索函数，如 日期 / 拼接 / IF" clearable class="st-control st-control--small fxe-search" />
            <div v-if="!fnKw" class="fxe-cats">
              <button type="button" v-for="c in ['全部', ...catalog.categories, '运算符']" :key="c" class="fxe-cat" :class="{ on: fnCat === c }" :aria-pressed="fnCat === c"
                    @click="fnCat = c">{{ c.replace('与时间函数', '').replace('函数', '') }}</button>
            </div>
            <div class="fxe-col-list">
              <template v-for="g in fnGroups" :key="g.title">
                <div v-if="fnGroups.length > 1" class="fxe-group">{{ g.title }}</div>
                <template v-if="g.ops">
                  <div v-for="o in g.items" :key="o.op" class="fxe-item" :class="{ on: hover?.key === `op:${o.op}` }"
                       @mouseenter="hover = opItem(o)" @mousedown.prevent @click="insertText(` ${o.op} `)">
                    <span class="fxe-item-name fxe-mono fxe-op-name">{{ o.op }}</span>
                  </div>
                </template>
                <template v-else>
                  <div v-for="fn in g.items" :key="`${g.title}:${fn.name}`" class="fxe-item" :class="{ on: hover?.key === `fn:${fn.name}` }"
                       @mouseenter="hover = fnItem(fn)" @mousedown.prevent @click="insertItem(fnItem(fn))">
                    <span class="fxe-item-name fxe-mono">{{ fn.name }}</span>
                  </div>
                </template>
              </template>
              <div v-if="!fnGroups.length" class="fxe-none">没有匹配的函数</div>
            </div>
          </div>
          <!-- 说明 -->
          <div class="fxe-doc">
            <template v-if="docItem?.kind === 'func'">
              <div class="fxe-doc-sig">{{ docItem.fn.signature }}</div>
              <div class="fxe-doc-desc">{{ docItem.fn.desc }}</div>
              <div class="fxe-doc-ex-t">示例 <span class="fxe-doc-ex-tip">点击示例可插入到公式</span></div>
              <div v-for="(ex, i) in docItem.fn.examples" :key="i" class="fxe-doc-ex" @mousedown.prevent @click="insertText(ex.code)">
                <code v-html="highlightName(ex.code, docItem.fn.name)" />
                <span class="fxe-doc-ex-r" :class="{ block: ex.result.startsWith('=') }">{{ ex.result.startsWith('=') ? ex.result : `，${ex.result}` }}</span>
                <span class="fxe-doc-ins">插入</span>
              </div>
              <div class="fxe-doc-note">注：[列名] 表示引用了同一条记录中此列的单元格参与公式计算；[#表.列名] 表示引用该表此列的所有值（整表引用）。</div>
              <template v-for="pm in docItem.fn.params || []" :key="pm.name">
                <div class="fxe-doc-pm-t">{{ pm.required ? '*' : '' }}{{ pm.name }}</div>
                <div class="fxe-doc-pm">{{ pm.desc || '—' }}</div>
              </template>
            </template>
            <template v-else-if="docItem?.kind === 'table'">
              <div class="fxe-doc-sig"><StIcon name="view-grid" :size="17" /> {{ docItem.table.label }}<span class="fxe-doc-tag">整表引用</span></div>
              <div class="fxe-doc-desc">引用整张表的所有记录，常用来统计记录数，或配合 FILTER 筛选。展开左侧的表可以引用某一列（该列所有记录的值）。</div>
              <div class="fxe-doc-ex-t">示例 <span class="fxe-doc-ex-tip">点击示例可插入到公式</span></div>
              <div v-for="(ex, i) in tableExamples(docItem.table)" :key="i" class="fxe-doc-ex" @mousedown.prevent @click="insertText(ex.code)">
                <code>{{ ex.show }}</code><span class="fxe-doc-ex-r">，{{ ex.result }}</span><span class="fxe-doc-ins">插入</span>
              </div>
            </template>
            <template v-else-if="docItem?.kind === 'tcol'">
              <div class="fxe-doc-sig"><StIcon :name="fieldIconName(docItem.field)" :size="17" /> {{ docItem.table.label }}.{{ docItem.field.label }}<span class="fxe-doc-tag">整列</span></div>
              <div class="fxe-doc-desc">「{{ docItem.table.label }}」中「{{ docItem.field.label }}」这一列所有记录的值，是一个列表。可配合 SUM / COUNTIF / SUMIF / LOOKUP / FILTER / UNIQUE 等函数使用；与值比较（如 = "北京"）时逐行比较，得到一列 TRUE/FALSE。</div>
              <div class="fxe-doc-ex-t">示例 <span class="fxe-doc-ex-tip">点击示例可插入到公式</span></div>
              <div v-for="(ex, i) in tcolExamples(docItem.table, docItem.field)" :key="i" class="fxe-doc-ex" @mousedown.prevent @click="insertText(ex.code)">
                <code>{{ ex.show }}</code><span class="fxe-doc-ex-r">，{{ ex.result }}</span><span class="fxe-doc-ins">插入</span>
              </div>
            </template>
            <template v-else-if="docItem?.kind === 'op'">
              <div class="fxe-doc-sig">{{ docItem.op.op }}<span class="fxe-doc-tag">运算符</span></div>
              <div class="fxe-doc-desc">{{ docItem.op.desc }}</div>
              <div class="fxe-doc-ex-t">示例</div>
              <div class="fxe-doc-ex" @mousedown.prevent @click="insertText(docItem.op.example)"><code>{{ docItem.op.example }}</code><span class="fxe-doc-ins">插入</span></div>
            </template>
            <template v-else-if="docItem?.kind === 'field'">
              <div class="fxe-doc-sig"><StIcon :name="fieldIconName(docItem.field)" :size="17" /> {{ docItem.field.label }}</div>
              <div class="fxe-doc-desc">{{ fieldTypeLabel(docItem.field) }}字段。{{ fieldHint(docItem.field) }}</div>
              <div class="fxe-doc-ex-t">第 {{ result?.row_no || 1 }} 行的值</div>
              <div class="fxe-doc-ex fxe-doc-val">{{ rowValues[docItem.field.field_name] || '（空）' }}</div>
            </template>
          </div>
        </div>
      </div>

      <section v-show="aiVisible" class="fxe-ai" :style="aiPosition" role="dialog" aria-label="AI 写公式" @keydown.esc.stop.prevent="aiVisible = false">
        <div class="fxe-ai-heading"><strong>AI 写公式</strong><button type="button" class="fxe-ico st-icon-action" aria-label="关闭 AI 写公式" @click="aiVisible = false"><StIcon name="close" :size="16" /></button></div>
        <label class="fxe-ai-hint" for="formula-ai-request">描述你想计算的结果，可以点击选择左侧的“表字段”</label>
        <AiFormulaAssistant ref="aiAssistantRef" :active="aiVisible" :table-id="tableId" @focus="fieldTarget = 'ai'" @apply="onAiApply" />
      </section>

      <!-- 光标处联想 -->
      <div v-if="acItems.length" ref="acRef" class="fxe-ac" @mousedown.prevent>
        <div v-for="(it, i) in acItems" :key="it.key" class="fxe-ac-item" :class="{ on: i === ac.index }"
             @mouseenter="ac.index = i" @click="insertItem(it)">
          <StIcon v-if="it.kind === 'field'" :name="fieldIconName(it.field)" :size="14" class="fxe-item-ico" />
          <StIcon v-else-if="it.kind === 'table'" name="view-grid" :size="14" class="fxe-item-ico" />
          <span v-else class="fxe-ac-fx">fx</span>
          <span class="fxe-ac-name" :class="{ 'fxe-mono': it.kind === 'func' }">{{ it.label }}</span>
          <span class="fxe-ac-desc">{{ it.kind === 'func' ? shortDesc(it.fn) : it.kind === 'table' ? '整表引用' : (rowValues[it.field.field_name] || '字段') }}</span>
          <span v-if="i === ac.index" class="fxe-tab">Tab</span>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import '../../../smart/fieldRichText.css'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { updateFormulaSelection } from '../../../smart/utils/formulaSelection.js'
import { vPanelDrag } from '../../../smart/utils/panelDrag.js'
import { useFloatingPanel } from '../../../smart/utils/floatingPanel.js'
import StIcon from '../icons/StIcon.vue'
import AiFormulaAssistant from '../ai/AiFormulaAssistant.vue'
import { FIELD_REGISTRY } from '../../../smart/registry/fieldRegistry.js'
import { fieldTypeIconSvg, fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { callContext, formatFormula, functionInsertion, referencedTableIds, splitSignature, tokenize } from '../../../smart/utils/formula.js'
import { getTable, smartFormulaFunctions, smartFormulaPreview, smartGetDoc, smartGetTree } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  title: { type: String, default: '公式' },
  formula: { type: String, default: '' },
  fields: { type: Array, default: () => [] },
  fieldName: { type: String, default: null },        // 正在编辑的公式字段（排除自引用）
  tableId: { type: Number, default: null },
  sampleRecordId: { type: Number, default: null },   // 当前视图首行（「第 1 行」与网格一致）
})
const emit = defineEmits(['close', 'save'])

// 运算符快捷条：back = 插入后光标回退的字符数（如 "" 把光标放进引号）
const OPS = [
  { v: ' + ', label: '+', tip: '加' }, { v: ' - ', label: '−', tip: '减' }, { v: ' * ', label: '×', tip: '乘' },
  { v: ' / ', label: '÷', tip: '除' }, { v: ' & ', label: '&', tip: '拼接文本' }, { v: ' = ', label: '=', tip: '等于' },
  { v: ' <> ', label: '≠', tip: '不等于' }, { v: ' > ', label: '>', tip: '大于' }, { v: ' >= ', label: '≥', tip: '大于等于' },
  { v: ' < ', label: '<', tip: '小于' }, { v: ' <= ', label: '≤', tip: '小于等于' }, { v: '()', label: '( )', tip: '括号', back: 1 },
  { v: '""', label: '" "', tip: '文本（引号）', back: 1 }, { v: ', ', label: ',', tip: '参数分隔' },
]

const panelRef = ref(null)
const layerRef = ref(null)
const acRef = ref(null)
const refreshPanel = useFloatingPanel(() => panelRef.value, () => layerRef.value)
const refreshAc = useFloatingPanel(() => acRef.value)
const editorRef = ref(null)
const catalog = ref({ categories: [], functions: [], operators: [] })
const catalogError = ref(false)
async function loadCatalog() {
  catalogError.value = false
  try { catalog.value = await smartFormulaFunctions() }
  catch { catalogError.value = true }
}
// 整表引用：文档内的表（sheet / 收集表单），字段按需加载
const tableMap = ref(new Map())     // id → {id, label, fields|null, self}
const token = ref('')
const ctx = ref(null)
const hover = ref(null)          // 字段/函数栏悬停项（说明栏优先展示）
const fieldKw = ref('')
const fnKw = ref('')
const fnCat = ref('全部')
const preview = reactive({ loading: false, data: null })
const rowValues = ref({})        // 第 1 行各字段展示值（字段栏右侧灰字）
const aiVisible = ref(false)
const aiPosition = ref({})
let aiAnchorObserver
function positionAi() {
  const rect = panelRef.value?.getBoundingClientRect()
  if (!rect || !aiVisible.value) return
  const width = Math.min(520, window.innerWidth - 24)
  const top = Math.max(12, Math.min(rect.top, window.innerHeight - 200))
  aiPosition.value = {
    left: `${Math.max(12, Math.min(rect.right + 12, window.innerWidth - width - 12))}px`,
    top: `${top}px`,
    maxHeight: `${window.innerHeight - top - 12}px`,
  }
}
watch(aiVisible, async active => {
  aiAnchorObserver?.disconnect()
  window.removeEventListener('resize', positionAi)
  if (!active) return
  await nextTick()
  positionAi()
  aiAnchorObserver = new MutationObserver(positionAi)
  if (panelRef.value) aiAnchorObserver.observe(panelRef.value, { attributes: true, attributeFilter: ['style'] })
  window.addEventListener('resize', positionAi)
})
onBeforeUnmount(() => {
  aiAnchorObserver?.disconnect()
  window.removeEventListener('resize', positionAi)
})
const aiAssistantRef = ref(null)
const fieldTarget = ref('formula')
function insertSelectedField(field) {
  if (aiVisible.value && fieldTarget.value === 'ai') aiAssistantRef.value?.insertField(field)
  else insertItem(fieldItem(field))
}
const srcText = ref('')
const ac = reactive({ x: 0, y: 0, index: 0 })
let savedRange = null

const result = computed(() => preview.data)
const refFields = computed(() => props.fields.filter(f => f.field_name !== props.fieldName))
const fnByName = computed(() => new Map(catalog.value.functions.map(f => [f.name, f])))
const fieldItem = (f) => ({ kind: 'field', key: `f:${f.field_name}`, label: f.label, field: f })
const tableItem = (t) => ({ kind: 'table', key: `t:${t.id}`, label: t.label, table: t })
const tcolItem = (t, f) => ({ kind: 'tcol', key: `tc:${t.id}.${f.field_name}`, label: `${t.label}.${f.label}`, table: t, field: f })
const opItem = (o) => ({ kind: 'op', key: `op:${o.op}`, label: o.op, op: o })
async function ensureFields(id) {
  const t = tableMap.value.get(id)
  if (!t || t.fields) return
  try {
    const meta = await getTable(id)
    t.fields = meta.fields
  } catch {
    t.fields = []
  }
  tableMap.value = new Map(tableMap.value)
}
async function loadTables() {
  const doc = await smartGetDoc()
  const tree = await smartGetTree(doc.id)
  const m = new Map()
  for (const e of tree.entries) {
    if (!e.ref_table_id || !['sheet', 'form'].includes(e.type)) continue
    const self = e.ref_table_id === props.tableId
    m.set(e.ref_table_id, { id: e.ref_table_id, label: e.name, self, fields: self ? props.fields : null })
  }
  tableMap.value = m
}
// 整表 / 整列示例（用真实表名字段名生成）
const firstOf = (t, types) => (t.fields || []).find(f => types.includes(f.field_type))
function tableExamples(t) {
  const txt = firstOf(t, ['text', 'singleSelect'])
  const out = [{ code: `COUNTA([#${t.id}])`, show: `COUNTA([${t.label}])`, result: `${t.label}的记录数` }]
  if (txt) out.push({ code: `FILTER([#${t.id}], [#${t.id}.${txt.field_name}]="").COUNTA()`, show: `FILTER([${t.label}], [${t.label}.${txt.label}]="").COUNTA()`, result: `${txt.label}为空的记录数` })
  return out
}
function tcolExamples(t, f) {
  const num = ['number', 'currency', 'percent', 'progress'].includes(f.field_type)
  const ref = `[#${t.id}.${f.field_name}]`
  const show = `[${t.label}.${f.label}]`
  if (num) {
    const key = firstOf(t, ['text', 'singleSelect'])
    const out = [{ code: `SUM(${ref})`, show: `SUM(${show})`, result: '该列合计' }, { code: `${ref}.MAX()`, show: `${show}.MAX()`, result: '该列最大值' }]
    if (key) {
      const local = refFields.value.find(x => ['text', 'singleSelect'].includes(x.field_type))
      out.push({ code: `SUMIF([#${t.id}.${key.field_name}], ${local ? `[${local.field_name}]` : '"条件"'}, ${ref})`,
                 show: `SUMIF([${t.label}.${key.label}], ${local ? `[${local.label}]` : '"条件"'}, ${show})`, result: `按${key.label}条件求和` })
    }
    return out
  }
  const local = refFields.value.find(x => x.field_type === f.field_type) || refFields.value[0]
  return [
    { code: `COUNTIF(${ref}, ${local ? `[${local.field_name}]` : '"值"'})`, show: `COUNTIF(${show}, ${local ? `[${local.label}]` : '"值"'})`, result: '该列中等于本行值的记录数' },
    { code: `UNIQUE(${ref}).COUNTA()`, show: `UNIQUE(${show}).COUNTA()`, result: '该列不重复的值个数' },
    { code: `${ref}.LISTJOIN("、")`, show: `${show}.LISTJOIN("、")`, result: '该列所有值连成文本' },
  ]
}
const fnItem = (fn) => ({ kind: 'func', key: `fn:${fn.name}`, label: fn.name, fn })
const shortDesc = (fn) => fn.desc.replace(/[。，,].*$/, '').slice(0, 14)

// ---------- 字段栏 / 函数栏 ----------
const fieldList = computed(() => {
  const k = fieldKw.value.trim().toLowerCase()
  return refFields.value.filter(f => !k || f.label.toLowerCase().includes(k))
})
function matchFn(fn, k) {
  return fn.name.toLowerCase().includes(k) || fn.desc.includes(k) || fn.category.includes(k) || (fn.keywords || '').includes(k)
    || fn.signature.toLowerCase().includes(k)
}
const fnGroups = computed(() => {
  const k = fnKw.value.trim().toLowerCase()
  if (k) {
    const seen = new Set()
    const items = catalog.value.functions.filter(fn => matchFn(fn, k) && !seen.has(fn.name) && seen.add(fn.name))
      .sort((a, b) => Number(!a.name.toLowerCase().startsWith(k)) - Number(!b.name.toLowerCase().startsWith(k)))
    return items.length ? [{ title: '搜索结果', items }] : []
  }
  const opsGroup = { title: '运算符', ops: true, items: catalog.value.operators || [] }
  if (fnCat.value === '运算符') return [opsGroup]
  const cats = fnCat.value === '全部' ? catalog.value.categories : [fnCat.value]
  const groups = cats.map(c => ({ title: c, items: catalog.value.functions.filter(f => f.category === c) })).filter(g => g.items.length)
  return fnCat.value === '全部' ? [...groups, opsGroup] : groups
})

// ---------- 光标处联想 ----------
const acItems = computed(() => {
  const k = token.value.trim().toUpperCase()
  if (!k) return []
  const uniq = [...new Map(catalog.value.functions.map(f => [f.name, f])).values()]
  const fns = uniq.filter(f => f.name.startsWith(k))
    .sort((a, b) => a.name.length - b.name.length || a.name.localeCompare(b.name))
    .concat(uniq.filter(f => !f.name.startsWith(k) && f.name.includes(k)))
  const fs = refFields.value.filter(f => f.label.toUpperCase().includes(k)).map(fieldItem)
  // 中文开头的输入更可能是字段名：字段排前
  const fieldFirst = /[一-龥]/.test(k[0])
  const list = fieldFirst ? [...fs, ...fns.map(fnItem)] : [...fns.map(fnItem), ...fs]
  return list.slice(0, 8)
})
watch(acItems, async () => {
  ac.index = 0
  await nextTick()
  if (acItems.value.length) { placeAc(); await refreshAc() }
})
watch(() => ac.index, () => nextTick(() => acRef.value?.querySelector('.on')?.scrollIntoView({ block: 'nearest' })))
watch(() => [props.visible, aiVisible.value], async ([visible]) => {
  if (visible) { await nextTick(); await refreshPanel(); if (acItems.value.length) await refreshAc() }
})

// 说明栏：联想高亮项（正在输入时）> 悬停项 > 光标所在函数 > IF
const docItem = computed(() => acItems.value[ac.index]
  || hover.value
  || (ctx.value && fnByName.value.get(ctx.value.name) ? fnItem(fnByName.value.get(ctx.value.name)) : null)
  || (fnByName.value.get('IF') ? fnItem(fnByName.value.get('IF')) : null))

const sigView = computed(() => {
  const fn = ctx.value?.name && fnByName.value.get(ctx.value.name)
  if (!fn) return null
  const parts = splitSignature(fn.signature)
  if (ctx.value.chained && parts.args.length) {
    const rest = parts.args.slice(1)
    return { prefix: parts.args[0].replace(/^\[|\]$/g, ''), head: parts.head, args: rest, tail: parts.tail,
             cur: rest.length ? Math.min(ctx.value.argIndex - 1, rest.length - 1) : -1 }
  }
  const n = parts.args.length
  return { prefix: '', head: parts.head, args: parts.args, tail: parts.tail, cur: n ? Math.min(ctx.value.argIndex, n - 1) : -1 }
})

// ---------- 编辑区：渲染 / 序列化 ----------
function chipEl(f) {
  const el = document.createElement('span')
  el.className = 'fxe-chip st-field-rich-chip'
  el.contentEditable = 'false'
  el.dataset.field = f.field_name
  el.innerHTML = `${fieldTypeIconSvg(fieldIconName(f), 13)}<span>${escapeHtml(f.label)}</span>`
  return el
}
// 整表 [#id] / 整列 [#id.字段] 胶囊（绿色系，与本行字段区分）
function tableChipEl(t, f = null) {
  const el = document.createElement('span')
  el.className = 'fxe-chip st-field-rich-chip fxe-chip-t'
  el.contentEditable = 'false'
  el.dataset.tref = f ? `#${t.id}.${f.field_name}` : `#${t.id}`
  const icon = f ? fieldTypeIconSvg(fieldIconName(f), 13) : fieldTypeIconSvg('text', 0)
  el.innerHTML = `${f ? icon : '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2.5" y="2.5" width="11" height="11" rx="1.5"/><path d="M8 2.5v11M2.5 8h11"/></svg>'}<span>${escapeHtml(f ? `${t.label}.${f.label}` : t.label)}</span>`
  return el
}
function escapeHtml(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]) }
function fragmentOf(src) {
  const frag = document.createDocumentFragment()
  for (const p of tokenize(src, props.fields, tableMap.value)) {
    if (p.t === 'field') { frag.appendChild(chipEl(p.field)); continue }
    if (p.t === 'table') { frag.appendChild(tableChipEl(p.table)); continue }
    if (p.t === 'tcol') { frag.appendChild(tableChipEl(p.table, p.field)); continue }
    p.v.split('\n').forEach((line, i) => {
      if (i) frag.appendChild(document.createElement('br'))
      if (line) frag.appendChild(document.createTextNode(line))
    })
  }
  return frag
}
function render(src) {
  const el = editorRef.value
  if (!el) return
  el.innerHTML = ''
  el.appendChild(fragmentOf(src))
  srcText.value = serialize()
}
function serializeNode(node) {
  let out = ''
  for (const n of node.childNodes) {
    if (n.nodeType === 3) out += n.nodeValue.replace(/ /g, ' ')
    else if (n.nodeType === 1) {
      if (n.dataset?.field) out += `[${n.dataset.field}]`
      else if (n.dataset?.tref) out += `[${n.dataset.tref}]`
      else if (n.tagName === 'BR') out += '\n'
      else if (n.tagName === 'DIV' || n.tagName === 'P') out += (out && !out.endsWith('\n') ? '\n' : '') + serializeNode(n)
      else out += serializeNode(n)
    }
  }
  return out
}
const serialize = () => (editorRef.value ? serializeNode(editorRef.value) : '')
function textBeforeCaret() {
  const sel = window.getSelection()
  if (!sel?.rangeCount || !editorRef.value?.contains(sel.anchorNode)) return serialize()
  const r = document.createRange()
  r.selectNodeContents(editorRef.value)
  r.setEnd(sel.anchorNode, sel.anchorOffset)
  const box = document.createElement('div')
  box.appendChild(r.cloneContents())
  return serializeNode(box)
}

// ---------- 光标 / 插入 ----------
function saveRange() {
  const sel = window.getSelection()
  if (sel?.rangeCount && editorRef.value?.contains(sel.anchorNode)) savedRange = sel.getRangeAt(0).cloneRange()
}
function onBlur() { saveRange(); token.value = '' }
function restoreRange() {
  const el = editorRef.value
  el.focus()
  const sel = window.getSelection()
  sel.removeAllRanges()
  if (savedRange && el.contains(savedRange.startContainer)) sel.addRange(savedRange)
  else {
    const r = document.createRange()
    r.selectNodeContents(el)
    r.collapse(false)
    sel.addRange(r)
  }
  return sel
}
function currentToken() {
  const sel = window.getSelection()
  if (!sel?.rangeCount) return ''
  const node = sel.anchorNode
  if (!node || node.nodeType !== 3 || !editorRef.value?.contains(node)) return ''
  if ((textBeforeCaret().match(/"/g) || []).length % 2) return ''   // 字符串内不联想
  const m = node.nodeValue.slice(0, sel.anchorOffset).match(/[A-Za-z_一-龥][A-Za-z0-9_一-龥]*$/)
  return m ? m[0] : ''
}
function placeAc() {
  const sel = window.getSelection()
  if (!sel?.rangeCount) return
  const r = sel.getRangeAt(0).cloneRange()
  let rect = r.getBoundingClientRect()
  if (!rect.height) {   // 空文本节点处折叠区间无尺寸：临时插入零宽标记测量
    const mark = document.createElement('span')
    mark.textContent = '​'
    r.insertNode(mark)
    rect = mark.getBoundingClientRect()
    mark.remove()
  }
  const width = Math.min(acRef.value?.getBoundingClientRect().width || 360, Math.max(0, window.innerWidth - 24))
  const height = Math.min(acRef.value?.getBoundingClientRect().height || 320, Math.max(0, window.innerHeight - 24))
  ac.x = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
  const below = rect.bottom + 6
  const top = below + height > window.innerHeight - 12 ? rect.top - height - 6 : below
  ac.y = Math.max(12, Math.min(top, window.innerHeight - height - 12))
  if (acRef.value) Object.assign(acRef.value.style, { left: `${ac.x}px`, top: `${ac.y}px` })
}
function onEditorMouseDown(event) {
  const chip = event.target.closest?.('.fxe-chip')
  if (!chip || event.button !== 0) return
  event.preventDefault()
  editorRef.value.focus()
  const range = document.createRange()
  range.selectNode(chip)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)
  onCaretMove()
}
onBeforeUnmount(() => globalThis.CSS?.highlights?.delete('formula-brackets'))
watch(() => props.visible, visible => { if (!visible) globalThis.CSS?.highlights?.delete('formula-brackets') })
function onCaretMove() {
  saveRange()
  if (editorRef.value) updateFormulaSelection(editorRef.value)
  token.value = currentToken()
  ctx.value = callContext(textBeforeCaret())
  if (token.value) placeAc()
}
function onKeyup(e) {
  if (['ArrowUp', 'ArrowDown', 'Tab', 'Enter', 'Escape'].includes(e.key) && acItems.value.length) return
  onCaretMove()
}
function onInput() {
  srcText.value = serialize()
  onCaretMove()
  schedulePreview()
}
function deleteToken(sel) {
  const t = token.value
  if (!t) return
  const node = sel.anchorNode
  if (node?.nodeType !== 3) return
  const off = sel.anchorOffset
  node.nodeValue = node.nodeValue.slice(0, off - t.length) + node.nodeValue.slice(off)
  const r = document.createRange()
  r.setStart(node, off - t.length)
  r.collapse(true)
  sel.removeAllRanges()
  sel.addRange(r)
}
function finishInsert(sel, range) {
  range.collapse(true)
  sel.removeAllRanges()
  sel.addRange(range)
  token.value = ''
  onInput()
}
function insertItem(it) {
  if (!it) return
  const sel = restoreRange()
  deleteToken(sel)
  const range = sel.getRangeAt(0)
  range.deleteContents()
  if (it.kind === 'field' || it.kind === 'table' || it.kind === 'tcol') {
    const chip = it.kind === 'field' ? chipEl(it.field) : tableChipEl(it.table, it.kind === 'tcol' ? it.field : null)
    range.insertNode(chip)
    range.setStartAfter(chip)
  } else {
    const takesArgs = !it.fn.signature.includes('()')
    const insertion = functionInsertion(textBeforeCaret(), it.fn.name, takesArgs)
    const text = document.createTextNode(insertion.text)
    range.insertNode(text)
    range.setStart(text, insertion.caret)
  }
  finishInsert(sel, range)
}
// 插入一段文本（运算符 / 示例）：示例里的 [字段] 自动转胶囊；back = 光标回退字符数
function insertText(text, back = 0) {
  const sel = restoreRange()
  const range = sel.getRangeAt(0)
  range.deleteContents()
  const frag = fragmentOf(text)
  const last = frag.lastChild
  range.insertNode(frag)
  if (last?.nodeType === 3 && back) range.setStart(last, Math.max(last.nodeValue.length - back, 0))
  else if (last) range.setStartAfter(last)
  finishInsert(sel, range)
}
function insertNewline() {
  const sel = restoreRange()
  const range = sel.getRangeAt(0)
  const br = document.createElement('br')
  range.insertNode(br)
  range.setStartAfter(br)
  if (!br.nextSibling) br.after(document.createElement('br'))
  finishInsert(sel, range)
}
function onKeydown(e) {
  if (acItems.value.length) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const n = acItems.value.length
      ac.index = (ac.index + (e.key === 'ArrowDown' ? 1 : -1) + n) % n
      return
    }
    if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); insertItem(acItems.value[ac.index]); return }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); token.value = ''; return }
  }
  if (e.key === 'Tab') { e.preventDefault(); return }
  if (e.key === 'Enter') { e.preventDefault(); insertNewline(); return }
  if (e.key === 'Escape') { e.stopPropagation(); emit('close') }
}
function onPaste(e) {
  e.preventDefault()
  insertText(e.clipboardData.getData('text/plain'))
}

// ---------- 试算（第 1 行） ----------
let timer = null
let seq = 0
function schedulePreview() {
  clearTimeout(timer)
  timer = setTimeout(runPreview, 350)
}
async function runPreview() {
  const src = serialize().trim()
  const my = ++seq
  preview.loading = true
  try {
    const r = await smartFormulaPreview(props.tableId, { formula: src, field_name: props.fieldName,
      ...(props.sampleRecordId ? { record_id: props.sampleRecordId, row_no: 1 } : {}) })
    if (my !== seq) return
    preview.data = r
    if (r.row_values) rowValues.value = r.row_values
  } catch (e) {
    if (my === seq) preview.data = { ok: false, blocking: false, error: { title: '试算失败', message: e.message } }
  } finally {
    if (my === seq) preview.loading = false
  }
}
// 语法/字段/循环错误不可保存；某行数据导致的计算错误允许保存（该行结果为空）
const canSave = computed(() => !!srcText.value.trim() && !!preview.data && !preview.loading && !preview.data.blank
  && (preview.data.ok || !preview.data.blocking))

function save() {
  const t = preview.data?.type
  emit('save', { formula: serialize().trim(), returnType: t === 'number' ? 'number' : t === 'date' ? 'date' : 'text' })
}
function format() {
  const src = serialize()
  if (!src.trim()) return
  render(formatFormula(src, catalog.value.functions.map(f => f.name)))
  placeCaretEnd()
  schedulePreview()
}
function onAiApply(r) {
  render(r.formula)
  placeCaretEnd()
  runPreview()
}
function placeCaretEnd() {
  const el = editorRef.value
  el.focus()
  const r = document.createRange()
  r.selectNodeContents(el)
  r.collapse(false)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(r)
  saveRange()
}

// ---------- 说明栏辅助 ----------
function highlightName(code, name) {
  return escapeHtml(code).replace(new RegExp(`\\b${name}\\b`, 'g'), `<b>${name}</b>`)
}
function fieldTypeLabel(f) { return FIELD_REGISTRY[f.field_type]?.label || '文本' }
function fieldHint(f) {
  const ft = f.field_type
  if (['singleSelect', 'multiSelect'].includes(ft)) return '公式中取选项文本，多选为多个值（可配合 COUNTA / TEXTJOIN 使用）。'
  if (['date', 'createdTime', 'lastModifiedTime'].includes(ft)) return '可配合 TEXT / DATEDIF / DATEADD 等日期函数使用。'
  if (['number', 'currency', 'percent', 'progress'].includes(ft)) return '可直接参与 + − × ÷ 运算。'
  if (ft === 'checkbox') return '值为 TRUE / FALSE，可直接作为 IF 的条件。'
  return '可用 & 或 CONCAT 拼接文本。'
}

watch(() => props.visible, async (v) => {
  if (!v) return
  aiVisible.value = false
  if (!catalog.value.functions.length) void loadCatalog()
  Object.assign(preview, { loading: false, data: null })
  rowValues.value = {}
  token.value = ''
  hover.value = null
  fieldKw.value = ''
  fnKw.value = ''
  fnCat.value = '全部'
  const tableIds = referencedTableIds(props.formula)
  if (tableIds.length) {
    await loadTables().catch(() => {})
    await Promise.all(tableIds.map(ensureFields))
  }
  await nextTick()
  render(props.formula || '')
  placeCaretEnd()
  ctx.value = callContext(serialize())
  runPreview()   // 空公式也调用：拿第 1 行各字段取值
}, { immediate: true })
</script>

<style scoped>
.fxe-mask { position: fixed; inset: 0; background: rgba(0, 0, 0, .25); display: flex; align-items: center; justify-content: center; --el-color-primary: var(--st-primary); }
.fxe { width: 900px; max-width: calc(100vw - 24px); height: 680px; max-height: calc(100vh - 24px); background: #fff; border-radius: 12px; overflow: auto;
       display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0, 0, 0, .18); }
/* ---- 上：紧凑输入区 ---- */
.fxe-top { background: #fff; flex: none; border-bottom: 1px solid var(--st-border); }
.fxe-head { display: flex; align-items: center; gap: 8px; padding: 12px 20px 8px; cursor: move; touch-action: none; }
.fxe-title { font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); margin-right: auto; }
.fxe-tool { display: inline-flex; align-items: center; gap: 5px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; height: 28px; box-sizing: border-box; padding: 0 8px; border: 0; background: transparent; font-family: inherit; border-radius: 4px; }
.fxe-tool:hover, .fxe-ico:hover { background: var(--st-bg-hover); }
.fxe-tool.active { color: var(--st-primary); background: var(--st-primary-weak); }
.fxe-vsep { width: 1px; height: 16px; background: var(--st-border); }
.fxe-ico { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 0; background: transparent; cursor: pointer; padding: 0; border-radius: 6px; color: var(--st-text-2); margin-left: 4px; }
.fxe-editor { min-height: 76px; max-height: 140px; box-sizing: border-box; overflow: auto; margin: 0 20px; padding: 8px 12px; border: 1px solid var(--st-border); border-radius: 8px;
              outline: none; color: var(--st-text-2); }
.fxe-editor:focus { border-color: var(--st-primary); box-shadow: 0 0 0 2px rgba(46, 107, 230, .12); }
.fxe-editor:empty::before { content: attr(data-placeholder); color: var(--st-text-4); font-family: var(--el-font-family); }
.fxe-editor :deep(.fxe-chip-t) { border-color: #2BB3A3; background: #E3F7F3; }
.fxe-editor :deep(.fxe-chip) { cursor: pointer; }
.fxe-editor :deep(.fxe-chip.is-selected) { background: #DCE9FF; outline: 2px solid #83ACFF; outline-offset: 1px; }
:global(::highlight(formula-brackets)) { background: #FFE6A3; color: #20242B; }
.fxe-ops { display: flex; align-items: center; gap: 4px; padding: 8px 20px 0; flex-wrap: wrap; }
.fxe-op { min-width: 28px; height: 28px; padding: 0 6px; box-sizing: border-box; display: inline-flex; align-items: center; justify-content: center;
          border: 1px solid var(--st-border); border-radius: 5px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; background: #fff; font-family: Menlo, Consolas, monospace; }
.fxe-op:hover { border-color: var(--st-primary); color: var(--st-primary); }
.fxe-ops-hint { margin-left: auto; font-size: 12px; color: var(--st-text-3); }
.fxe-result { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 20px 12px; }
.fxe-res-main { display: flex; align-items: flex-start; gap: 8px; min-height: 28px; font-size: var(--st-font-size); color: var(--st-text-2); min-width: 0; }
.fxe-res-dim { color: var(--st-text-3); font-size: var(--st-font-size); line-height: 26px; }
.fxe-res-label { white-space: nowrap; line-height: 24px; color: var(--st-text-2); }
.fxe-res-val { line-height: 24px; word-break: break-all; font-weight: 500; }
.fxe-err-t { color: #F54A45; font-weight: 700; line-height: 24px; }
.fxe-err-m { font-size: var(--st-font-size); color: var(--st-text-2); }
.fxe-ok { min-width: 64px; height: 28px; flex: none; }
/* ---- 签名条 ---- */
.fxe-sig { flex: none; padding: 8px 20px; line-height: 20px; background: #F7F8FA; font-size: var(--st-font-size); color: var(--st-text-2); border-bottom: 1px solid var(--st-border); font-family: Menlo, Consolas, monospace; min-height: 36px; box-sizing: border-box; }
.fxe-sig-dim { color: var(--st-text-3); font-family: var(--el-font-family); font-size: var(--st-font-size); }
.fxe-sig-cur { background: #FDE6A3; border-radius: 3px; }
/* ---- 下：三栏 ---- */
.fxe-ai { position: fixed; z-index: 1; width: 520px; max-width: calc(100vw - 24px); max-height: calc(100vh - 24px); box-sizing: border-box; overflow-x: hidden; overflow-y: auto; scrollbar-width: none; padding: 16px; border: 1px solid var(--st-border); border-radius: 12px; background: #F7F8FA; box-shadow: 0 8px 32px rgba(0, 0, 0, .18); }
.fxe-ai::-webkit-scrollbar { display: none; }
.fxe-ai-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; color: var(--st-text-1); }
.fxe-ai-hint { color: var(--st-text-3); font-size: 12px; font-weight: 400; }
.fxe-ai :deep(.afa) { margin-top: 6px; }
.fxe-panes { flex: 1 1 240px; display: flex; min-height: 240px; overflow-x: auto; }
.fxe-col { display: flex; flex-direction: column; min-height: 0; border-right: 1px solid var(--st-border); }
.fxe-col-fields { width: 28%; min-width: 220px; flex: none; }
.fxe-col-funcs { width: 220px; flex: none; }
.fxe-col-funcs .fxe-item-name { max-width: 100%; }
.fxe-col-head { display: flex; align-items: baseline; justify-content: space-between; padding: 12px 16px 10px; font-size: var(--st-font-size); font-weight: 600; color: var(--st-text-1); }
.fxe-col-sub { font-size: var(--st-font-size); font-weight: 400; color: var(--st-text-3); }
.fxe-tabs { display: inline-flex; gap: 14px; }
.fxe-tab-btn { cursor: pointer; color: var(--st-text-3); font-weight: 500; padding-bottom: 3px; border-bottom: 2px solid transparent; }
.fxe-tab-btn.on { color: var(--st-text-1); border-bottom-color: var(--st-primary); font-weight: 600; }
.fxe-caret { display: inline-flex; color: var(--st-text-3); padding: 2px; margin-left: -4px; border-radius: 4px; transition: transform .15s; }
.fxe-caret.open { transform: rotate(90deg); }
.fxe-caret:hover { background: #D9DBDE; }
.fxe-self { font-size: 11px; color: var(--st-primary); background: var(--st-primary-weak); border-radius: 3px; padding: 0 5px; }
.fxe-sub { padding-left: 34px; }
.fxe-op-name { min-width: 30px; }
.fxe-doc-note { background: #fff; border-radius: 8px; padding: 10px 14px; font-size: var(--st-font-size); color: var(--st-text-2); line-height: 1.7; margin: 4px 0 16px; }
.fxe-doc-pm-t { font-size: var(--st-font-size); font-weight: 700; color: var(--st-text-1); margin: 10px 0 6px; }
.fxe-doc-pm { background: #fff; border-radius: 8px; padding: 10px 14px; font-size: var(--st-font-size); color: var(--st-text-2); line-height: 1.7; }
.fxe-doc-tag { font-size: 11px; font-weight: 400; font-family: var(--el-font-family); color: #0F7B6C; background: #D6F4EE; border-radius: 3px; padding: 1px 6px; margin-left: 4px; }
.fxe-search { --st-control-size: 28px; width: calc(100% - 32px); margin: 0 16px 8px; box-sizing: border-box; flex: none; }
.fxe-cats { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 16px 8px; }
.fxe-cat { height: 28px; box-sizing: border-box; border: 0; font-family: inherit; font-size: 12px; padding: 0 8px; border-radius: 4px; background: #F2F3F5; color: var(--st-text-2); cursor: pointer; }
.fxe-cat.on { background: var(--st-primary); color: #fff; }
.fxe-col-list { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 0 8px 12px; }
.fxe-group { font-size: var(--st-font-size); color: var(--st-text-3); padding: 10px 10px 4px; }
.fxe-item { display: flex; align-items: center; gap: 8px; padding: 0 10px; border-radius: 6px; cursor: pointer; font-size: var(--st-font-size); color: var(--st-text-2);  height: var(--st-list-item-height); box-sizing: border-box; }
.fxe-item.on { background: var(--st-primary-weak, #EAF1FE); }
.fxe-item-ico { color: var(--st-text-2); flex: none; }
.fxe-item-name { flex: none; max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fxe-item-val { flex: 1; min-width: 0; text-align: right; font-size: var(--st-font-size); color: var(--st-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fxe-mono { font-family: Menlo, Consolas, monospace; font-size: var(--st-font-size); }
.fxe-none { padding: 20px 10px; color: var(--st-text-4); font-size: var(--st-font-size); }
.fxe-doc { flex: 1 0 280px; overflow: auto; overscroll-behavior: contain; background: #F7F8FA; padding: 16px 20px; min-width: 280px; box-sizing: border-box; }
.fxe-doc-sig { font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); line-height: 1.5; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-family: Menlo, Consolas, monospace; }
.fxe-doc-desc { overflow-wrap: anywhere; font-size: var(--st-font-size); color: var(--st-text-2); margin: 10px 0 14px; line-height: 1.7; }
.fxe-doc-ex-t { font-size: var(--st-font-size); font-weight: 700; color: var(--st-text-1); margin-bottom: 8px; }
.fxe-doc-ex-tip { font-size: var(--st-font-size); font-weight: 400; color: var(--st-text-3); margin-left: 6px; }
.fxe-doc-ex { position: relative; background: #fff; border: 1px solid transparent; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: var(--st-font-size);
              color: var(--st-text-2); line-height: 1.8; cursor: pointer; }
.fxe-doc-ex:hover { border-color: var(--st-primary); }
.fxe-doc-ex code { overflow-wrap: anywhere; font-family: Menlo, Consolas, monospace; color: var(--st-text-2); }
.fxe-doc-ex code :deep(b) { color: var(--st-text-2); }
.fxe-doc-ex-r { color: var(--st-text-3); }
.fxe-doc-ex-r.block { display: block; }
.fxe-doc-ins { position: absolute; right: 10px; top: 10px; font-size: var(--st-font-size); color: var(--st-primary); display: none; }
.fxe-doc-ex:hover .fxe-doc-ins { display: inline; }
.fxe-doc-val { cursor: default; color: var(--st-text-2); font-size: var(--st-font-size); word-break: break-all; }
.fxe-doc-val:hover { border-color: transparent; }
/* ---- 光标处联想 ---- */
.fxe-ac { position: fixed; width: 360px; max-width: calc(100vw - 24px); max-height: min(320px, calc(100vh - 24px)); box-sizing: border-box; overflow: auto; background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; }
.fxe-ac-item { display: flex; align-items: center; gap: 8px; padding: 0 10px; border-radius: 6px; cursor: pointer; font-size: var(--st-font-size);  height: var(--st-list-item-height); box-sizing: border-box; }
.fxe-ac-item.on { background: #E6E8EB; }
.fxe-ac-fx { font-size: 11px; font-style: italic; color: var(--st-primary); width: 14px; flex: none; }
.fxe-ac-name { flex: none; color: var(--st-text-2); }
.fxe-ac-desc { flex: 1; min-width: 0; font-size: var(--st-font-size); color: var(--st-text-4); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fxe-tab { font-size: 11px; color: var(--st-text-2); background: #D9DBDE; border-radius: 3px; padding: 0 5px; flex: none; }
.fxe-ac-name { max-width: 55%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fxe-sig, .fxe-err-m { overflow-wrap: anywhere; }
.fxe-tool:focus-visible, .fxe-ico:focus-visible, .fxe-op:focus-visible, .fxe-cat:focus-visible { outline: 2px solid var(--st-primary); outline-offset: 2px; }
.fxe-cat:hover:not(.on) { background: var(--st-bg-hover); }
@media (max-width: 540px) {
  .fxe-head { flex-wrap: wrap; padding: 12px 12px 4px; gap: 4px; }
  .fxe-title { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .fxe-tool { padding: 4px; }
  .fxe-editor { margin-left: 12px; margin-right: 12px; }
  .fxe-ops, .fxe-result, .fxe-sig { padding-left: 12px; padding-right: 12px; }
  .fxe-res-main { flex-wrap: wrap; overflow-wrap: anywhere; }
}
</style>
