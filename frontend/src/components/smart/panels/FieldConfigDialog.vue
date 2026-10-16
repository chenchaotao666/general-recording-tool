<template>
  <!-- 字段配置弹窗（设计文档 §3.2 统一骨架）：名称 + 类型下拉 + 类型专属配置区 + 确定/取消 -->
  <el-dialog :model-value="visible" :title="field ? '修改字段' : '添加列'" width="480px"
             @update:model-value="$emit('close')" destroy-on-close>
    <div class="cfg">
      <el-input v-model="form.label" placeholder="字段名称" class="cfg-name" />
      <el-select :teleported="false" v-model="form.field_type" class="cfg-type" :disabled="!!field && isSystemLike"
                 @change="onTypeChange">
        <el-option-group v-for="g in FIELD_TYPE_GROUPS" :key="g" :label="g">
          <el-option v-for="(reg, ft) in typesOf(g)" :key="ft" :value="ft" :label="reg.label">
            <span class="ft-opt"><StIcon :name="ft" :size="14" />{{ reg.label }}</span>
          </el-option>
        </el-option-group>
      </el-select>

      <!-- 单选/多选：选项编辑（设计稿：列-单选-添加选项 / 列-单选-引用选项） -->
      <template v-if="['singleSelect', 'multiSelect'].includes(form.field_type)">
        <div class="cfg-sec">
          <div class="sec-head">
            <span class="sec-title">选项</span>
            <span class="sec-head-right">
              <el-checkbox :model-value="isRef" size="small" @change="toggleRef">引用选项</el-checkbox>
              <el-tooltip content="选项集来自其他表的单选/多选字段，源表变更自动同步" placement="top">
                <span class="info-icon">ⓘ</span>
              </el-tooltip>
            </span>
          </div>

          <!-- 手动选项：⊖删除 | 色块 | 名称 | ⠿拖拽排序 -->
          <template v-if="!isRef">
            <div class="opt-list">
              <div v-for="(o, i) in form.config.options" :key="o.id" class="opt-row"
                   :class="{ 'drag-over': dragOverIdx === i && dragIdx !== i }"
                   draggable="true" @dragstart="onDragStart(i, $event)" @dragend="onDragEnd"
                   @dragover.prevent="dragOverIdx = i" @dragleave="dragOverIdx === i && (dragOverIdx = -1)"
                   @drop.prevent="onDrop(i)">
                <span class="del" title="删除选项" @click="form.config.options.splice(i, 1)">⊖</span>
                <el-color-picker :model-value="optionColor(o.color).value" size="small" class="opt-color"
                                 @change="(v) => { o.color = nearestColor(v) }" />
                <el-input v-model="o.label" size="small" />
                <span class="drag-handle" title="拖拽调整顺序">⠿</span>
              </div>
            </div>
            <el-button link type="primary" size="small" class="opt-add" @click="addOption">⊕ 添加选项</el-button>
            <el-checkbox v-model="form.config.allowAddOptionWhenEditing" size="small">允许填写时新增选项</el-checkbox>
          </template>

          <!-- 引用选项：引用表 + 引用字段；联动条件（设计文档 §3.3） -->
          <template v-else>
            <div class="ref-row">
              <el-select :teleported="false" v-model="form.config.reference.tableId" size="small"
                         placeholder="选择表" filterable @change="form.config.reference.fieldId = null">
                <el-option v-for="t in tables" :key="t.id" :value="t.id" :label="t.label" />
              </el-select>
              <el-select :teleported="false" v-model="form.config.reference.fieldId" size="small"
                         placeholder="选择字段（单选/多选）">
                <el-option v-for="f in refSelectFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
              </el-select>
            </div>
            <div class="linkage-toggle">
              <el-checkbox :model-value="linkageEnabled" size="small" @change="toggleLinkage">启用选项联动</el-checkbox>
              <el-tooltip content="本表当前行字段值与引用表行字段值比较，满足条件的引用行其值才作为可选项" placement="top">
                <span class="info-icon">ⓘ</span>
              </el-tooltip>
            </div>
            <div v-if="linkageEnabled" class="linkage-box">
              <div class="linkage-head">
                <span class="sec-title">联动条件</span>
                <span class="linkage-match">满足以下
                  <el-select :teleported="false" v-model="form.config.optionLinkage.match" size="small"
                             class="match-select">
                    <el-option value="all" label="全部条件" />
                    <el-option value="any" label="任一条件" />
                  </el-select>
                </span>
              </div>
              <div v-for="(c, i) in form.config.optionLinkage.conditions" :key="i" class="seg-row">
                <el-select :teleported="false" v-model="c.localFieldId" size="small" placeholder="本表字段">
                  <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
                </el-select>
                <el-select :teleported="false" v-model="c.operator" size="small" style="width: 76px">
                  <el-option value="eq" label="等于" />
                </el-select>
                <el-select :teleported="false" v-model="c.remoteFieldId" size="small" placeholder="引用表字段">
                  <el-option v-for="f in refFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
                </el-select>
                <span class="del" @click="form.config.optionLinkage.conditions.splice(i, 1)">⊖</span>
              </div>
              <el-button link type="primary" size="small"
                         @click="form.config.optionLinkage.conditions.push({ localFieldId: null, operator: 'eq', remoteFieldId: null })">＋ 添加条件</el-button>
            </div>
          </template>
        </div>
      </template>

      <!-- 数字/百分数/货币/进度 -->
      <template v-if="['number', 'percent', 'currency'].includes(form.field_type)">
        <div class="cfg-sec">
          <el-select :teleported="false" v-model="form.config.precision" size="small" class="sec-item">
            <el-option value="default" label="默认小数位" />
            <el-option v-for="n in [0, 1, 2, 3, 4]" :key="n" :value="n" :label="`${n} 位小数`" />
          </el-select>
          <el-checkbox v-model="form.config.thousandSeparator" size="small">使用千位符</el-checkbox>
        </div>
      </template>
      <template v-if="form.field_type === 'currency'">
        <div class="cfg-sec">
          <el-select :teleported="false" v-model="form.config.currencyCode" size="small" class="sec-item">
            <el-option v-for="(s, c) in CURRENCIES" :key="c" :value="c" :label="`${c} - ${s}`" />
          </el-select>
        </div>
      </template>
      <template v-if="form.field_type === 'progress'">
        <div class="cfg-sec">
          <el-input-number v-model="form.config.range.min" size="small" />
          <span>—</span>
          <el-input-number v-model="form.config.range.max" size="small" />
          <el-checkbox v-model="form.config.showNumber" size="small">展示数字</el-checkbox>
        </div>
      </template>

      <!-- 日期 -->
      <template v-if="['date', 'createdTime', 'lastModifiedTime'].includes(form.field_type)">
        <div class="cfg-sec">
          <el-select :teleported="false" v-model="form.config.format" size="small" class="sec-item">
            <el-option value="yyyy-MM-dd" label="2018-04-20" />
            <el-option value="yyyy/MM/dd" label="2018/4/20" />
            <el-option value="yyyy年M月d日" label="2018年4月20日" />
            <el-option value="yyyy-MM-dd HH:mm" label="2018-04-20 15:30" />
          </el-select>
          <el-checkbox v-if="form.field_type === 'date'" v-model="form.config.autoFillCreatedTime" size="small">默认填充创建时间</el-checkbox>
        </div>
      </template>

      <!-- 人员 -->
      <template v-if="form.field_type === 'member'">
        <div class="cfg-sec">
          <el-checkbox v-model="form.config.multiple" size="small">允许添加多个人员</el-checkbox>
          <el-checkbox v-model="form.config.notifyOnAdd" size="small">添加人员时通知他</el-checkbox>
        </div>
      </template>

      <!-- 复选框 -->
      <template v-if="form.field_type === 'checkbox'">
        <div class="cfg-sec"><el-checkbox v-model="form.config.defaultChecked" size="small">默认勾选</el-checkbox></div>
      </template>

      <!-- 自动编号 -->
      <template v-if="form.field_type === 'autoNumber'">
        <div class="cfg-sec col">
          <el-radio-group v-model="form.config.numberType" size="small">
            <el-radio-button value="autoIncrement">自增数字</el-radio-button>
            <el-radio-button value="custom">自定义编号</el-radio-button>
          </el-radio-group>
          <template v-if="form.config.numberType === 'custom'">
            <div class="seg-preview">预览：{{ segPreview }}</div>
            <div v-for="(s, i) in form.config.segments" :key="i" class="seg-row">
              <el-select :teleported="false" v-model="s.type" size="small" style="width: 110px">
                <el-option value="autoIncrement" label="自增数字" />
                <el-option value="fixedText" label="固定字符" />
                <el-option value="createDate" label="创建日期" />
              </el-select>
              <el-input-number v-if="s.type === 'autoIncrement'" v-model="s.digits" :min="1" :max="8" size="small" />
              <el-input v-if="s.type === 'fixedText'" v-model="s.text" size="small" placeholder="请输入" />
              <el-select :teleported="false" v-if="s.type === 'createDate'" v-model="s.format" size="small">
                <el-option value="yyyyMMdd" label="20261013" />
                <el-option value="yyyy-MM-dd" label="2026-10-13" />
                <el-option value="yyyyMM" label="202610" />
              </el-select>
              <span class="del" @click="form.config.segments.splice(i, 1)">⊖</span>
            </div>
            <el-button link type="primary" size="small" @click="form.config.segments.push({ type: 'fixedText', text: '' })">＋ 添加编号字段</el-button>
          </template>
        </div>
      </template>

      <!-- 公式 -->
      <template v-if="form.field_type === 'formula'">
        <div class="cfg-sec col">
          <el-input v-model="form.config.formula" type="textarea" :rows="3"
                    placeholder='公式表达式，如 [数字] * 2（字段用 [字段名] 引用；函数：iff/abs/round/min/max/year/month/day/datediff/concat 等）' />
          <el-select :teleported="false" v-model="form.config.returnType" size="small" class="sec-item">
            <el-option value="text" label="返回：文本" />
            <el-option value="number" label="返回：数字" />
          </el-select>
        </div>
      </template>

      <!-- 关联 -->
      <template v-if="form.field_type === 'relation'">
        <div class="cfg-sec col">
          <el-select :teleported="false" v-model="form.config.targetTableId" size="small" placeholder="关联的智能表" filterable>
            <el-option v-for="t in tables" :key="t.id" :value="t.id" :label="t.label" />
          </el-select>
          <el-checkbox v-model="form.config.multiple" size="small">允许多选</el-checkbox>
        </div>
      </template>

      <!-- 查找引用 -->
      <template v-if="form.field_type === 'lookup'">
        <div class="cfg-sec col">
          <el-select :teleported="false" v-model="form.config.sourceTableId" size="small" placeholder="要引用的表" filterable
                     @change="form.config.sourceFieldId = null">
            <el-option v-for="t in tables" :key="t.id" :value="t.id" :label="t.label" />
          </el-select>
          <el-select :teleported="false" v-model="form.config.sourceFieldId" size="small" placeholder="要引用的字段">
            <el-option v-for="f in sourceFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
          </el-select>
          <el-select :teleported="false" v-model="form.config.aggregation" size="small" class="sec-item">
            <el-option v-for="(l, k) in LOOKUP_AGGS" :key="k" :value="k" :label="l" />
          </el-select>
          <div v-for="(c, i) in form.config.conditions" :key="i" class="seg-row">
            <el-select :teleported="false" v-model="c.sourceFieldId" size="small" placeholder="引用表的字段">
              <el-option v-for="f in sourceFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
            </el-select>
            <el-select :teleported="false" v-model="c.op" size="small" style="width: 80px">
              <el-option value="eq" label="等于" /><el-option value="contains" label="包含" />
            </el-select>
            <el-select :teleported="false" v-model="c.rightFieldId" size="small" placeholder="本表的字段" clearable>
              <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
            </el-select>
            <span class="del" @click="form.config.conditions.splice(i, 1)">⊖</span>
          </div>
          <el-button link type="primary" size="small"
                     @click="form.config.conditions.push({ sourceFieldId: null, op: 'eq', rightFieldId: null })">＋ 添加条件</el-button>
        </div>
      </template>
    </div>
    <template #footer>
      <div class="dlg-footer">
        <!-- AI 匹配标签：设计文档 §18 划在 V3，本轮占位 -->
        <el-button v-if="['singleSelect', 'multiSelect'].includes(form.field_type)" text class="ai-btn"
                   @click="ElMessage.info('AI 匹配标签将在 V3 版本提供，敬请期待')"><StIcon name="sparkle" :size="14" /> 使用 AI 匹配标签</el-button>
        <span v-else />
        <span>
          <el-button @click="$emit('close')">取消</el-button>
          <el-button type="primary" :disabled="!form.label" @click="save">确定</el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import { FIELD_REGISTRY, FIELD_TYPE_GROUPS, optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  field: Object,          // 编辑态传入现有字段；新增为 null
  preset: { type: Object, default: null },   // 新增预设 {field_type, label}（AddFieldPop 类型网格跳入）
  fields: { type: Array, default: () => [] },   // 本表字段（lookup 条件右值用）
  tables: { type: Array, default: () => [] },   // 可选的关联/引用目标表
  sourceFieldsOf: { type: Function, default: () => () => [] },  // (tableId) => Promise<fields[]>
})
const emit = defineEmits(['close', 'save'])

const CURRENCIES = { CNY: '￥', USD: '$', EUR: '€', JPY: '¥', HKD: 'HK$', GBP: '£' }
const LOOKUP_AGGS = { raw: '原样引用', rawDistinct: '去重引用', sum: '求和', count: '计数', countDistinct: '去重计数', avg: '平均值', max: '最大值', min: '最小值' }

const form = reactive({ label: '', field_type: 'text', config: {} })
const srcFields = ref([])
let lastSelectCfg = null   // 弹窗内最近一次单选/多选配置（选项在单选↔多选间切换时保留）

watch(() => props.visible, async (v) => {
  if (!v) return
  lastSelectCfg = null
  if (props.field) {
    form.label = props.field.label
    form.field_type = props.field.field_type || 'text'
    form.config = JSON.parse(JSON.stringify(props.field.options || {}))
    normalizeConfig()
  } else {
    // 新增：可带预设（AddFieldPop 类型网格选定后跳入）
    form.label = props.preset?.label || ''
    form.field_type = props.preset?.field_type || 'text'
    form.config = FIELD_REGISTRY[form.field_type].defaultConfig()
    normalizeConfig()
    if (!form.label && props.preset?.field_type) form.label = FIELD_REGISTRY[form.field_type].label
  }
})

const isSystemLike = computed(() => ['createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime'].includes(props.field?.field_type))

function typesOf(group) {
  return Object.fromEntries(Object.entries(FIELD_REGISTRY).filter(([, r]) => r.group === group))
}
function onTypeChange(ft) {
  // 单选/多选互换（含经其他类型中转）时保留已配选项，不被 defaultConfig 清空
  if (Array.isArray(form.config?.options)) {
    lastSelectCfg = { options: form.config.options, allow: form.config.allowAddOptionWhenEditing }
  }
  form.config = FIELD_REGISTRY[ft].defaultConfig()
  if (['singleSelect', 'multiSelect'].includes(ft) && lastSelectCfg) {
    form.config.options = lastSelectCfg.options
    if (lastSelectCfg.allow !== undefined) form.config.allowAddOptionWhenEditing = lastSelectCfg.allow
  }
  normalizeConfig()
  if (!form.label) form.label = FIELD_REGISTRY[ft].label
}
function normalizeConfig() {
  if (['singleSelect', 'multiSelect'].includes(form.field_type)) {
    const c = form.config
    if (!c.options) c.options = []
    if (!c.optionSource) c.optionSource = 'manual'
    if (!c.reference) c.reference = { tableId: null, fieldId: null }
    if (!c.optionLinkage) c.optionLinkage = { enabled: false, match: 'all', conditions: [] }
  }
  if (form.field_type === 'progress' && !form.config.range) form.config.range = { min: 0, max: 100 }
  if (form.field_type === 'autoNumber' && !form.config.segments) form.config.segments = [{ type: 'autoIncrement', digits: 3 }]
  if (form.field_type === 'lookup' && !form.config.conditions) form.config.conditions = []
}

// ---------- 单选/多选：引用选项 / 选项联动 / 拖拽排序 ----------
const isRef = computed(() => form.config?.optionSource === 'reference')
const linkageEnabled = computed(() => !!form.config?.optionLinkage?.enabled)

function toggleRef(v) {
  form.config.optionSource = v ? 'reference' : 'manual'
}
function toggleLinkage(v) {
  form.config.optionLinkage.enabled = v
}

// 引用表的字段（选项源候选=单选/多选；联动条件右值=全部字段）
const refFields = ref([])
const refSelectFields = computed(() =>
  refFields.value.filter(f => ['singleSelect', 'multiSelect'].includes(f.field_type)))
watch(() => form.config?.reference?.tableId, async (tid) => {
  refFields.value = tid ? await props.sourceFieldsOf(tid) : []
})

// HTML5 拖拽排序：dragstart 记源、drop 移动并重排 order
const dragIdx = ref(-1)
const dragOverIdx = ref(-1)
function onDragStart(i, e) {
  dragIdx.value = i
  e.dataTransfer.effectAllowed = 'move'
}
function onDrop(i) {
  const from = dragIdx.value
  if (from < 0 || from === i) return
  const opts = form.config.options
  opts.splice(i, 0, opts.splice(from, 1)[0])
  opts.forEach((o, idx) => { o.order = idx })
}
function onDragEnd() {
  dragIdx.value = -1
  dragOverIdx.value = -1
}

const sourceFields = computed(() => srcFields.value)
watch(() => form.config?.sourceTableId, async (tid) => {
  srcFields.value = tid ? await props.sourceFieldsOf(tid) : []
})

let optSeq = 1
function addOption() {
  const opts = form.config.options
  const id = `opt_${Date.now()}_${optSeq++}`
  opts.push({ id, label: `选项${opts.length + 1}`, color: 'blue', order: opts.length })
}
function nearestColor(v) {
  return v || 'blue'   // el-color-picker 给 hex；色板 key 由渲染层 optionColor 兜底
}

const segPreview = computed(() => {
  if (form.field_type !== 'autoNumber') return ''
  return (form.config.segments || []).map(s => {
    if (s.type === 'autoIncrement') return '0'.repeat(Math.max(1, (s.digits || 3) - 1)) + '1'
    if (s.type === 'fixedText') return s.text || ''
    return '20261013'
  }).join('')
})

function save() {
  const config = { ...form.config }
  if (['singleSelect', 'multiSelect'].includes(form.field_type)) {
    // 按 schema 组装（设计文档 §3.3）：manual 不带 reference/optionLinkage；联动未启用不带 optionLinkage
    if (config.optionSource === 'reference') {
      if (!config.reference?.tableId || !config.reference?.fieldId) {
        ElMessage.warning('引用选项需要选择引用的表和字段')
        return
      }
      delete config.allowAddOptionWhenEditing   // 引用模式下该配置不适用（前端整块隐藏）
      if (!config.optionLinkage?.enabled) delete config.optionLinkage
      else config.optionLinkage = {
        enabled: true, match: config.optionLinkage.match === 'any' ? 'any' : 'all',
        conditions: (config.optionLinkage.conditions || []).filter(c => c.localFieldId && c.remoteFieldId),
      }
    } else {
      config.optionSource = 'manual'
      delete config.reference
      delete config.optionLinkage
    }
  }
  emit('save', { label: form.label, field_type: form.field_type, config })
}
</script>

<style scoped>
.cfg { display: flex; flex-direction: column; gap: 10px; }
.cfg-name { font-weight: 600; }
.cfg-sec { border-top: 1px solid var(--el-border-color-lighter); padding-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.cfg-sec.col { align-items: flex-start; }
.sec-title { font-size: 12px; color: var(--el-text-color-secondary); }
.sec-item { width: 220px; }
.opt-row, .seg-row { display: flex; align-items: center; gap: 6px; }
.del { cursor: pointer; color: var(--el-color-danger); }
.seg-preview { font-size: 12px; color: var(--el-text-color-secondary); background: var(--el-fill-color-light); padding: 4px 8px; border-radius: 4px; }
/* 选项区（设计稿：列-单选-添加选项） */
.sec-head { display: flex; align-items: center; justify-content: space-between; }
.sec-head-right { display: flex; align-items: center; gap: 4px; }
.info-icon { color: var(--el-text-color-secondary); cursor: help; font-size: 12px; }
.opt-list { display: flex; flex-direction: column; gap: 4px; }
.opt-row { padding: 2px 4px; border-radius: 4px; background: var(--el-fill-color-lighter); }
.opt-row.drag-over { box-shadow: 0 -2px 0 var(--el-color-primary); }
.opt-row .el-input { flex: 1; }
.opt-color { flex: none; }
.drag-handle { cursor: grab; color: var(--el-text-color-secondary); padding: 0 4px; user-select: none; }
.opt-add { align-self: flex-start; }
/* 引用选项（设计稿：列-单选-引用选项） */
.ref-row { display: flex; gap: 8px; }
.ref-row .el-select { flex: 1; }
.linkage-toggle { display: flex; align-items: center; gap: 4px; }
.linkage-box { background: var(--el-fill-color-lighter); border-radius: 6px; padding: 8px 10px; display: flex; flex-direction: column; gap: 8px; }
.linkage-head { display: flex; align-items: center; justify-content: space-between; }
.linkage-match { font-size: 12px; color: var(--el-text-color-secondary); display: flex; align-items: center; gap: 4px; }
.match-select { width: 96px; }
.dlg-footer { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.ft-opt { display: inline-flex; align-items: center; gap: 8px; }
.ft-opt .st-icon { color: var(--st-text-2); }
.ai-btn { color: var(--st-ai); background: transparent; border: none; }
.ai-btn:hover { color: var(--st-ai); background: var(--st-bg-hover); }
</style>
