<template>
  <!-- 单选/多选单元格编辑器（设计稿：单元格输入-单选.png）：
       锚定单元格显示当前标签（✕清除）+ 下拉按钮（上下双箭头）；下拉浮层 teleport 到 body，
       顶部搜索「查找或添加选项」，标签列表 ✓ 选中态；单选点选即提交，多选关闭时提交。
       closed（单击选中态）：只显示锚点不展开面板；点下拉按钮/双击锚点 → open 进编辑 -->
  <!-- 整个锚点框都是展开/收起热区（@click.stop 不再透传到 vxe 单元格点击——
       锚点自己管理开合，避免网格双击检测与选中逻辑双重处理）；✕ 与 ▼/▲ 自带 stop -->
  <span ref="anchorRef" class="sel-anchor" :class="{ closed }"
        @click.stop="onAnchorClick"
        @dblclick.stop="closed && $emit('open')">
    <span v-for="o in selectedOptions" :key="o.id" class="opt-tag"
          :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">
      <span class="opt-label">{{ o.label }}</span><span class="tag-x" title="清除" @click.stop="removeOption(o.id)">✕</span>
    </span>
    <!-- 未匹配到选项的原始值兜底（改类型/引用源被删场景） -->
    <span v-for="(v, i) in unmatchedValues" :key="`raw-${i}`" class="opt-tag raw"><span class="opt-label">{{ v }}</span></span>
    <!-- 下拉按钮：单个三角，点击切换展开/收起（方向随状态翻转） -->
    <span class="chev" title="展开/收起选项" @click.stop="onChevClick"><StIcon :name="closed ? 'caret-down' : 'caret-up'" :size="10" /></span>
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
import StIcon from '../icons/StIcon.vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'
import { filterLinkageOptions } from '../../../smart/utils/refOptions.js'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
  frozen: { type: Boolean, default: false },   // 列是否被冻结（判断显示副本在哪个 wrapper）
  closed: { type: Boolean, default: false },   // 单击选中态：只显示锚点，不展开面板
})
const emit = defineEmits(['commit', 'commit-soft', 'cancel', 'add-option', 'open', 'collapse'])

// 选项联动上下文：SmartTablePage 提供 Map(field_name → {linkage, remoteRows, refFieldId})
const refContext = inject('smartRefContext', { value: new Map() })

const cfg = computed(() => props.field.options || {})
const isMulti = computed(() => props.field.field_type === 'multiSelect')

// 多选用草稿（关闭时一次性提交）；单选点选即提交，无需草稿
const cur = props.record[props.field.field_name]
// 多选兜底包成数组（单选刚改多选时存量值可能还是标量 id，不能丢）
const draft = ref(isMulti.value
  ? (Array.isArray(cur) ? [...cur] : (cur == null || cur === '' ? [] : [cur]))
  : (cur ?? null))

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
// 下拉按钮：closed 点击=展开进编辑；open 点击=收起面板（回选中态，不取消选中）
function onChevClick() {
  if (props.closed) emit('open')
  else collapse()
}
// 锚点框整体同为开合热区（点击任意非 ✕ 位置）
function onAnchorClick() {
  if (props.closed) emit('open')
  else collapse()
}
// 收起面板回选中态（区别于 close 的完全退出）：草稿软提交（父级只落库不关编辑器，
// 未改动时父级按 sameCellValue 跳过写库），再通知父级回到选中态
function collapse() {
  emit('commit-soft', isMulti.value ? (draft.value.length ? [...draft.value] : null) : draft.value)
  emit('collapse')
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
    // 选中态（面板未展开）：✕ 直接生效；展开态：只改草稿不关面板，关闭时统一提交
    if (props.closed) emit('commit', draft.value.length ? [...draft.value] : null)
  } else if (props.closed) {
    emit('commit', null)
  } else {
    draft.value = null   // 展开态单选：✕ 只清空草稿，面板保持打开，关闭时按草稿提交
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
  // 展开态单选：✕ 清空过草稿（与当前值不同）则提交，否则视为取消
  else if (!props.closed && draft.value !== cur) emit('commit', draft.value)
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

// 面板锚定锚点框（锚点随标签换行增高，面板要跟到底边）：ResizeObserver 跟踪锚点尺寸
let anchorRO = null
function updateRect() {
  const r = anchorRef.value?.getBoundingClientRect()
  if (r) rect.value = r
}

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
  updateRect()
  anchorRO = new ResizeObserver(updateRect)
  anchorRO.observe(anchorRef.value)
  document.addEventListener('mousedown', onDocMousedown, true)
  nextTick(() => kwRef.value?.focus({ preventScroll: true }))
}))
onUnmounted(() => {
  anchorRO?.disconnect()
  document.removeEventListener('mousedown', onDocMousedown, true)
})
</script>

<style scoped>
.sel-anchor {
  /* 选中态与编辑态统一：标签放不下换行、向下展开成浮层框（边框对齐单元格外沿），
     打开下拉时锚点不回单行——选项始终完整可见；▼/▲ 钉在右上角。
     min-height 撑满宿主高度（行高调大后框依然占满单元格）；safe center：
     单行内容垂直居中（与查看态一致不跳），多行溢出时自动回落顶对齐 */
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap; align-content: safe center;
  width: 100%; min-height: 100%; box-sizing: border-box;
  background: #fff; border: 2px solid var(--el-color-primary); border-radius: 2px;
  padding: 3px 26px 3px 6px;   /* 右侧 26px 给 ▼/▲ 留位 */
  position: relative; z-index: 2; align-self: flex-start;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .12);
  user-select: none; cursor: pointer;   /* 选项文字不可选中；整框是开合热区 */
}
/* 选中态的宿主单元格还带着 8px padding 和 wrapper 的 -2px 光学上移：
   左边距 -8px 左移，宽度 +16px 补回左右两侧（负右边距只会拉动后续元素，不会加宽自身），
   高度 +16px 补回上下 padding，使边框盒与单元格外沿严格对齐；编辑态 padding 已归零，无需补偿 */
.sel-anchor.closed { margin: -6px 0 0 -8px; width: calc(100% + 16px); min-height: calc(100% + 16px); }
.sel-anchor .chev { position: absolute; top: 5px; right: 5px; margin-left: 0; }
.opt-tag { display: inline-flex; align-items: center; padding: 1px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap; max-width: 100%; box-sizing: border-box; }
/* 单个标签超宽时省略号截断，✕ 始终保留 */
.opt-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opt-tag.raw { background: var(--el-fill-color); color: var(--el-text-color-secondary); }
.tag-x { margin-left: 4px; cursor: pointer; opacity: .6; flex: none; }
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
  user-select: none;   /* 选项文字不可选中（搜索框内文字除外） */
}
.sel-search {
  width: 100%; box-sizing: border-box; border: none; outline: none;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 4px 2px 8px; font-size: 13px; color: var(--el-text-color-primary);
  user-select: text;
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
/* 面板挂 body 后拿不到 vxe 单元格的 22px 行高，标签会比单元格里矮一截——补齐一致 */
.sel-panel .opt-tag { line-height: 22px; }
.sel-item.create { color: var(--el-color-primary); font-size: 13px; padding-left: 22px; }
.sel-empty { color: var(--el-text-color-secondary); font-size: 12px; padding: 8px 2px; }
</style>
