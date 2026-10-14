<template>
  <!-- 单选/多选单元格编辑器（设计稿：单元格输入-单选.png）：
       锚定单元格显示当前标签（✕清除）+ 下拉按钮（上下双箭头）；下拉浮层 teleport 到 body，
       顶部搜索「查找或添加选项」，标签列表 ✓ 选中态；单选点选即提交，多选关闭时提交。
       closed（单击选中态）：只显示锚点不展开面板；点下拉按钮/双击锚点 → open 进编辑 -->
  <span ref="anchorRef" class="sel-anchor" :class="{ closed }" @dblclick.stop="closed && $emit('open')">
    <span v-for="o in selectedOptions" :key="o.id" class="opt-tag"
          :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">
      {{ o.label }}<span class="tag-x" title="清除" @click.stop="removeOption(o.id)">✕</span>
    </span>
    <!-- 未匹配到选项的原始值兜底（改类型/引用源被删场景） -->
    <span v-for="(v, i) in unmatchedValues" :key="`raw-${i}`" class="opt-tag raw">{{ v }}</span>
    <!-- 下拉按钮：单个三角，点击切换展开/收起（方向随状态翻转） -->
    <span class="chev" title="展开/收起选项" @click.stop="onChevClick">{{ closed ? '▼' : '▲' }}</span>
  </span>
  <teleport to="body">
    <div v-if="rect && !closed" ref="panelRef" class="sel-panel" :style="panelStyle" @mousedown.stop>
      <input ref="kwRef" v-model="kw" class="sel-search" placeholder="查找或添加选项"
             @keydown.enter.prevent="onEnter" @keydown.esc.stop.prevent="onEsc" />
      <div class="sel-kind">{{ isMulti ? '多选' : '单选' }}</div>
      <div class="sel-list">
        <div v-for="o in visibleOptions" :key="o.id" class="sel-item" @click="pick(o.id)">
          <span class="check">{{ isSelected(o.id) ? '✓' : '' }}</span>
          <span class="opt-tag"
                :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
        </div>
        <div v-if="creatable" class="sel-item create" @click="create">＋ 创建「{{ kw.trim() }}」</div>
        <div v-if="!visibleOptions.length && !creatable" class="sel-empty">无可选项</div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'
import { filterLinkageOptions } from '../../../smart/utils/refOptions.js'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
  frozen: { type: Boolean, default: false },   // 列是否被冻结（判断显示副本在哪个 wrapper）
  closed: { type: Boolean, default: false },   // 单击选中态：只显示锚点，不展开面板
})
const emit = defineEmits(['commit', 'cancel', 'add-option', 'open'])

// 选项联动上下文：SmartTablePage 提供 Map(field_name → {linkage, remoteRows, refFieldId})
const refContext = inject('smartRefContext', { value: new Map() })

const cfg = computed(() => props.field.options || {})
const isMulti = computed(() => props.field.field_type === 'multiSelect')

// 多选用草稿（关闭时一次性提交）；单选点选即提交，无需草稿
const cur = props.record[props.field.field_name]
const draft = ref(isMulti.value ? (Array.isArray(cur) ? [...cur] : []) : (cur ?? null))

// 可用选项：引用模式 + 启用联动时按当前行过滤（选项集本身已由 SmartTablePage 解析进 field.options.options）
const baseOptions = computed(() => {
  const opts = cfg.value.options || []
  const ctx = refContext.value.get(props.field.field_name)
  if (ctx?.linkage?.enabled) {
    return filterLinkageOptions(opts, ctx.linkage, props.record, ctx.remoteRows, ctx.refFieldId)
  }
  return opts
})

const kw = ref('')
const visibleOptions = computed(() => {
  const k = kw.value.trim()
  return k ? baseOptions.value.filter(o => o.label.includes(k)) : baseOptions.value
})
// 搜索无精确匹配且允许新增 → 展示创建行（引用模式禁创建）
const creatable = computed(() => {
  const k = kw.value.trim()
  return !!k && cfg.value.optionSource !== 'reference'
    && cfg.value.allowAddOptionWhenEditing !== false
    && !baseOptions.value.some(o => o.label === k)
})

const selectedOptions = computed(() => {
  const opts = cfg.value.options || []
  const ids = isMulti.value ? draft.value : (draft.value == null ? [] : [draft.value])
  return ids.map(id => opts.find(o => o.id === id)).filter(Boolean)
})
const unmatchedValues = computed(() => {
  const opts = cfg.value.options || []
  const ids = isMulti.value ? draft.value : (draft.value == null ? [] : [draft.value])
  return ids.filter(id => id != null && id !== '' && !opts.some(o => o.id === id)).map(String)
})

function isSelected(id) {
  return isMulti.value ? draft.value.includes(id) : draft.value === id
}
// 下拉按钮：closed 点击=展开进编辑；open 点击=收起（单选不改动，多选提交草稿）
function onChevClick() {
  if (props.closed) emit('open')
  else close()
}
function pick(id) {
  if (isMulti.value) {
    const i = draft.value.indexOf(id)
    if (i >= 0) draft.value.splice(i, 1)
    else draft.value.push(id)
  } else {
    emit('commit', id)   // 单选点选即提交，父级关闭编辑器
  }
}
function removeOption(id) {
  if (isMulti.value) {
    draft.value = draft.value.filter(x => x !== id)
    emit('commit', draft.value.length ? [...draft.value] : null)
  } else {
    emit('commit', null)
  }
}
function create() {
  emit('add-option', kw.value.trim())   // 父级落库新选项并提交新 optionId，随后关闭编辑器
}
function onEnter() {
  if (creatable.value) return create()
  if (visibleOptions.value.length === 1) pick(visibleOptions.value[0].id)
}
function close() {
  if (isMulti.value) emit('commit', draft.value.length ? [...draft.value] : null)
  else emit('cancel')
}
function onEsc() { close() }

// ---------- 浮层定位与外部点击关闭（复用文本浮层模式） ----------
const anchorRef = ref(null)
const panelRef = ref(null)
const kwRef = ref(null)
const rect = ref(null)
const panelStyle = computed(() => {
  const r = rect.value
  if (!r) return {}
  return { left: `${r.left}px`, top: `${r.bottom + 2}px`, minWidth: `${Math.max(r.width, 200)}px` }
})

function onDocMousedown(e) {
  const inPanel = panelRef.value?.contains(e.target)
  const inAnchor = anchorRef.value?.contains(e.target)
  if (!inPanel && !inAnchor) close()
}

onMounted(() => nextTick(() => {
  const td = anchorRef.value?.closest('td') || anchorRef.value?.parentElement
  // vxe 冻结列的单元格渲染三份（main/fixed-left/fixed-right wrapper）；非显示副本惰性，
  // 不开面板不聚焦，避免多实例互抢焦点（td 的 fixed--hidden 类挂载时不存在，按 wrapper 判断）
  const inFixed = !!td?.closest?.('.vxe-table--fixed-left-wrapper, .vxe-table--fixed-right-wrapper')
  if (inFixed !== props.frozen) return
  if (props.closed) return   // 单击选中态：只显示锚点，不展开面板、不监听外部点击
  rect.value = td?.getBoundingClientRect() || null
  document.addEventListener('mousedown', onDocMousedown, true)
  nextTick(() => kwRef.value?.focus({ preventScroll: true }))
}))
onUnmounted(() => document.removeEventListener('mousedown', onDocMousedown, true))
</script>

<style scoped>
.sel-anchor {
  display: flex; align-items: center; gap: 4px; width: 100%; height: 100%;
  padding: 0; box-sizing: border-box; overflow: hidden;   /* closed 态：单元格自带 8px padding，锚点不再加 */
}
.sel-anchor:not(.closed) { padding: 0 8px; }   /* 编辑态单元格 padding 归零，锚点补回 8px——两态标签位置与查看态一致 */
.opt-tag { padding: 1px 8px; border-radius: 6px; font-size: 12px; white-space: nowrap; }
.opt-tag.raw { background: var(--el-fill-color); color: var(--el-text-color-secondary); }
.tag-x { margin-left: 4px; cursor: pointer; opacity: .6; }
.tag-x:hover { opacity: 1; }
/* 下拉按钮（设计稿 PixPin_2026-10-15_00-56-40）：浅灰圆角小方块 + 单三角，点击切换展开/收起 */
.chev {
  margin-left: auto; flex: none; cursor: pointer;
  width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center;
  background: var(--el-fill-color); color: var(--el-text-color-secondary);
  border-radius: 4px; font-size: 8px; line-height: 1;
}
.chev:hover { background: var(--el-fill-color-dark); color: var(--el-text-color-primary); }
.sel-panel {
  position: fixed; z-index: 3000; background: #fff; border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .12); border: 1px solid var(--el-border-color-lighter);
  padding: 8px; box-sizing: border-box; max-width: 320px;
}
.sel-search {
  width: 100%; box-sizing: border-box; border: none; outline: none;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 4px 2px 8px; font-size: 13px; color: var(--el-text-color-primary);
}
.sel-search::placeholder { color: var(--el-text-color-placeholder); }
.sel-kind { font-size: 12px; color: var(--el-text-color-secondary); padding: 8px 2px 4px; }
.sel-list { max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; }
.sel-item {
  display: flex; align-items: center; gap: 6px; padding: 3px 4px;   /* 行高与单元格标签一致（标签 20px + 上下 3px） */
  cursor: pointer; border-radius: 4px;
}
.sel-item:hover { background: var(--el-fill-color-lighter); }
.sel-item .check { width: 16px; color: var(--el-color-primary); font-size: 12px; flex: none; }
.sel-item.create { color: var(--el-color-primary); font-size: 13px; padding-left: 22px; }
.sel-empty { color: var(--el-text-color-secondary); font-size: 12px; padding: 8px 2px; }
</style>
