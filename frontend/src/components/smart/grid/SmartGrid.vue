<template>
  <!-- SmartGrid：智能表网格（vxe-table 封装）。
       flatten 行序列：分组标题行 / 数据行（树形缩进）。添加一行入口在统计行左侧「＋」。
       视图配置（显隐/列序/列宽/冻结/行高/填色）纯前端应用，数据层不动（设计文档 §1.3 原则 1）。 -->
  <div class="smart-grid" :class="{ 'is-empty': !gridRows.length }" :style="{ maxWidth: `${gridContentWidth}px` }" @contextmenu.prevent @mouseover="onRowOver" @mouseleave="scheduleExpandHide" @wheel.capture="onGridWheel">
    <textarea ref="typingBuffer" class="grid-typing-buffer" tabindex="-1" aria-label="输入以替换选中单元格" @input="onSelectedInput" @compositionstart="typingComposing = true" @compositionend="finishSelectedComposition" />
    <!-- :key="t_colSig"：列序/列集变化时整表重挂载。vxe 列注册只在挂载时按 DOM 位次进行，
         增量重挂载会与静态列/编组竞态导致顺序错乱，整表重挂载保证按 headerTree 顺序干净注册 -->
    <vxe-table
      ref="gridRef"
      :key="`t_${colSig}`"
      class="smart-vxe"
      :class="{ 'rh-tall': rowHeightPx > 36 }"
      :style="{ '--rh-lines': rowLines, '--header-row-height': `${headerRowHeight}px`, '--image-cell-height': `${rowHeightPx - 1}px` }"
      :data="gridRows"
      :max-height="height"
      border
      :row-config="{ height: rowHeightPx, isHover: true, keyField: '__key' }"
      :column-config="{ resizable: true }"
      :scroll-y="{ enabled: true, gt: 100 }"
      :scroll-x="{ enabled: true, gt: 20 }"
      :show-footer="true"
      :footer-method="footerMethod"
      :footer-cell-config="{ height: 45 }"
      :row-class-name="rowClass"
      :cell-class-name="cellClass"
      :cell-style="cellFillStyle"
      :header-cell-style="headerCellStyle"
      :header-cell-class-name="headerCellClass"
      :footer-cell-class-name="footerCellClass"
      :header-cell-config="{ height: headerRowHeight }"
      :menu-config="menuConfig"
      @cell-click="onCellClick"
      @cell-dblclick="onCellDblClick"
      @header-cell-click="onHeaderClick"
      @footer-cell-click="onFooterClick"
      @header-cell-dblclick="onHeaderDblClick"
      @scroll="onGridScroll"
      @checkbox-all="onCheckAll"
      @checkbox-change="onCheckChange"
    >
      <vxe-column type="checkbox" width="36" fixed="left" align="center" header-align="center" class-name="col-ck" header-class-name="col-ck" />
      <vxe-column width="39" fixed="left" title="#" :params="{ rowNumber: true }" align="center" header-align="center" class-name="col-no" header-class-name="col-no">
        <template #default="{ row }">
          <span v-if="row.__rowType === 'group'" class="group-toggle" @click.stop="$emit('toggle-group', row.key)">
            {{ collapsedGroups.has(row.key) ? '▸' : '▾' }}
          </span>
          <span v-else-if="!row.__rowType" class="row-no">{{ row.__no }}</span>
        </template>
        <!-- 统计行左侧：添加一行「＋」（居中，设计稿 PixPin_2026-10-15_20-03-52 位置） -->
        <template #footer>
          <span v-if="canCreate" class="footer-add-btn" data-smart-tip="添加一行">＋</span>
        </template>
      </vxe-column>

      <!-- 编组（两级表头）+ 散列字段列（key 带 colSig：列序变化时重挂载以触发 vxe 重注册） -->
      <template v-for="node in headerTree" :key="`${node.key}:${colSig}`">
        <vxe-colgroup v-if="node.isGroup" :title="node.name" :fixed="node.fixed" header-align="center" :params="{ group: node.group }">
          <template #header>
            <span class="colgroup-title">
              <span class="cg-name">{{ node.name }}</span>
              <CellDropdown class="cg-caret" label="编组操作" @click="(e) => $emit('group-menu', node.group, e)" />
            </span>
          </template>
          <vxe-column v-for="f in node.fields" :key="f.field_name" :field="f.field_name"
                      :width="colWidths[f.field_name] || 160"
                      :fixed="node.fixed">
            <template #header><FieldHeader :field="f" :view="view" :lines="1" :readonly="readonly" :menu-open="menuField === f.field_name"
                         @filter="(r) => $emit('field-filter', f, r)" @menu="(e) => $emit('field-menu', f, e)" /></template>
            <template #default="{ row }"><CellSlot :row="row" :field="f" /></template>
            <template #footer><FooterCell :field="f" /></template>
          </vxe-column>
        </vxe-colgroup>
        <vxe-column v-else :field="node.field.field_name" :width="colWidths[node.field.field_name] || 160"
                    :fixed="node.fixed">
          <template #header><FieldHeader :field="node.field" :view="view" :lines="hasColGroups ? 3 : 2" :readonly="readonly" :menu-open="menuField === node.field.field_name"
                       @filter="(r) => $emit('field-filter', node.field, r)" @menu="(e) => $emit('field-menu', node.field, e)" /></template>
          <template #default="{ row }"><CellSlot :row="row" :field="node.field" /></template>
          <template #footer><FooterCell :field="node.field" /></template>
        </vxe-column>
      </template>

      <!-- 末尾「+」添加列：跟在最后一列后面随表格横向滚动（不冻结） -->
      <vxe-column width="48" align="center" header-align="center" header-class-name="th-add-col" :params="{ addField: true }">
        <template #header>
          <span class="add-col" aria-label="添加一列">＋</span>
        </template>
        <template #default><span /></template>
      </vxe-column>
    </vxe-table>
    <!-- 展开记录按钮（参照 单元格输入/hover-行.png）：hover 行或单击/双击行内单元格时出现，
         骑在表格左边框上（一半在表格外）。表体滚动容器会裁剪溢出内容，所以挂 body 按行位置定位。
         独立组件渲染：滚动时位置逐帧更新只重绘按钮本身，不触发整表重渲染（否则拖滚动条时表格抖动） -->
    <RowExpandBtn />
    <CellContextMenu v-if="cellMenu" :x="cellMenu.x" :y="cellMenu.y" :has-field="!!cellMenu.field"
      :can-create="canCreate" :can-delete="canDelete" :readonly="readonly"
      @action="onMenuAction" @close="cellMenu = null" />
    <!-- AI 列 / AI 单元格选中时：右侧浮出「✦ | ▾」生成按钮 -->
    <AiRunButton v-if="aiBtn && !readonly" :x="aiBtn.x" :y="aiBtn.y" :mode="aiBtn.mode" @run="onAiBtnRun" />
    <!-- 双击不可编辑的单元格：单元格下方提示（参照 PixPin_2026-10-17_16-22-09）「自动编号不可直接编辑 修改设置」 -->
    <teleport to="body">
      <div v-if="blockedHint" class="st-blocked-hint" :style="{ left: `${blockedHint.x}px`, top: `${blockedHint.y}px` }" @mousedown.stop>
        <span>{{ blockedHint.text }}</span>
        <span v-if="blockedHint.field" class="st-blocked-link" @click="openBlockedConfig">修改设置</span>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { Teleport, computed, h, nextTick, onActivated, onDeactivated, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import SmartCell from './SmartCell.vue'
import CellContextMenu from './CellContextMenu.vue'
import SmartCellEditor from './SmartCellEditor.vue'
import ProgressCell from './ProgressCell.vue'
import SelectCellPanel from './SelectCellPanel.vue'
import ImageCellPanel from './ImageCellPanel.vue'
import FileCellPanel from './FileCellPanel.vue'
import LinkCellPanel from './LinkCellPanel.vue'
import RelationCellPanel from './RelationCellPanel.vue'
import CellDropdown from './CellDropdown.vue'
import FieldHeader from './FieldHeader.vue'
import AiRunButton from '../ai/AiRunButton.vue'
import { isDisplayCell, visibleCellRect } from '../../../smart/utils/vxeCell.js'
import StIcon from '../icons/StIcon.vue'
import { BLOCKED_CONFIGURABLE, BLOCKED_EDIT_TEXT, regOf, sortDirectionLabels, STAT_LABELS, formatStatValue, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { nextCell } from '../../../smart/utils/cellNavigation.js'
import { evalFillRules, evalRowFill, headerFillColor } from '../../../smart/utils/format.js'
import { buildColumnLayout } from '../../../smart/utils/columnLayout.js'
import { currentFindKey, findCellKey, findMatchKeys, orderFindMatches } from '../../../smart/utils/findReplace.js'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },        // grid 接口行序列（可能含 __rowType:'group'）
  grouped: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
  aggregations: { type: Object, default: () => ({}) },
  view: { type: Object, default: () => ({ config: {} }) },
  columnGroups: { type: Array, default: () => [] },
  height: { type: [Number, String], default: 480 },
  collapsedGroups: { type: Object, default: () => new Set() },
  readonly: { type: Boolean, default: false },
  canCreate: { type: Boolean, default: false },
  canDelete: { type: Boolean, default: false },
  // 单元格级可编辑判定（内容权限：行级编辑范围 / 字段三态，V3）；缺省全部可编辑
  canEditCell: { type: Function, default: null },
  menuField: { type: String, default: null },   // 列头菜单当前打开的字段（三角保持展开态）
  activeRowId: { type: [Number, String], default: null },   // 右侧详情面板打开的记录（行高亮 + 展开按钮常显）
  searchMatches: { type: Array, default: () => [] },
  searchCurrentIndex: { type: Number, default: -1 },
})
const emit = defineEmits(['cell-commit', 'add-row', 'add-field', 'cell-menu', 'field-menu', 'toggle-group',
                          'selection-change', 'open-config', 'footer-menu', 'add-option', 'group-menu', 'add-row-in-group', 'ai-run',
                          'field-edit', 'field-filter', 'group-edit', 'expand-row'])

const gridRef = ref(null)
const editingCell = ref(null)   // {key, fieldName}

const viewConfig = computed(() => props.view?.config || {})
// 行高：档位或自定义行数（数字 N = 可容纳 N 行文字）
const rowHeightPx = computed(() => {
  const rh = viewConfig.value.rowHeight
  if (typeof rh === 'number') return Math.max(36, 14 + 22 * rh)
  return { default: 36, medium: 52, tall: 76, extraTall: 100 }[rh] || 36
})
// 行高能容纳的文本行数（行高 = 22px/行 + 上下留白）：默认 1 行、中 2、高 3、超高 4、自定义 N 行
const rowLines = computed(() => Math.max(1, Math.floor((rowHeightPx.value - 8) / 22)))
const colWidths = computed(() => viewConfig.value.colWidths || {})
const fillRules = computed(() => viewConfig.value.fillRules || [])

// 视图配置应用：显隐 + 列序
const visibleFields = computed(() => {
  const vis = viewConfig.value.fieldVisibility || {}
  let fs = props.fields.filter(f => vis[f.field_name] !== false)
  const order = viewConfig.value.fieldOrder
  if (order?.length) {
    const idx = new Map(order.map((n, i) => [n, i]))
    fs = [...fs].sort((a, b) => (idx.get(a.field_name) ?? 999) - (idx.get(b.field_name) ?? 999))
  }
  return fs
})

// 列序签名：vxe 的列注册（assembleColumn）只在列组件挂载时按 DOM 位次进行——
// v-for 同 key 重排不会重注册，列序变更不生效。把签名并入 key，顺序一变整列重挂载强制重注册
const headerTree = computed(() => buildColumnLayout(
  visibleFields.value, props.columnGroups, viewConfig.value.frozenFieldId))
const displayedFields = computed(() => headerTree.value.flatMap(n => n.isGroup ? n.fields : [n.field]))
// VXE 的边框绘制在列宽之内，无需额外加宽，否则末列右侧会露出第二条边框。
const gridContentWidth = computed(() => 36 + 39 + 48 + displayedFields.value.reduce((sum, f) => sum + Number(colWidths.value[f.field_name] || 160), 0))
const colSig = computed(() => JSON.stringify(headerTree.value.map(n => [
  n.key, n.fixed, n.isGroup ? n.fields.map(f => f.field_name) : n.field.field_name,
])))

// 表头行高（参照 表头样式.png）：无编组单层 46px（字段名可放 2 行）；
// 有编组每层 44px——编组内字段 1 行，散列字段纵跨两层 88px 可放 3 行。放不下才省略
const hasColGroups = computed(() => headerTree.value.some(n => n.isGroup))
const headerRowHeight = computed(() => (hasColGroups.value ? 44 : 46))
const groupedFieldNames = computed(() => new Set(headerTree.value.filter(n => n.isGroup).flatMap(n => n.fields.map(f => f.field_name))))
// 有编组时散列字段（纵跨两层）顶对齐：首行与编组标题同一水平线；整列选中态
function headerCellClass({ column }) {
  const cls = []
  if (column.type === 'checkbox' || column.params?.rowNumber) {
    cls.push('th-utility')
    if (hasColGroups.value) cls.push('th-utility-grouped')
  }
  if (hasColGroups.value && column.field && !groupedFieldNames.value.has(column.field)) cls.push('th-span')
  // 编组表头被选中：组头框左/右/上边
  if (!column.field && selectedGroupId.value != null && column.params?.group?.id === selectedGroupId.value) {
    cls.push('th-col-selected', 'sel-l', 'sel-r', 'sel-t')
  } else if (column.field) {
    const edge = selEdges(column.field)
    // 选中编组时，成员列表头上方是组头，不画上边；成员列下拉三角不常显（只留组头的）
    if (edge) cls.push('th-col-selected', ...edge, ...(selectedGroupId.value != null ? ['sel-member'] : ['sel-t']))
  }
  return cls.join(' ')
}
function footerCellClass({ column }) {
  if (column.params?.rowNumber && props.canCreate) return 'footer-add-cell'
  const edge = selEdges(column.field)
  return edge ? ['tf-col-selected', 'sel-b', ...edge].join(' ') : ''
}

// ---------- 整列选中（单击表头，参照 PixPin_2026-10-17_14-34-12）/ 双击表头 = 修改字段 ----------
// 单击字段表头选中该列；单击编组表头选中整组（组头 + 成员列作为一个整体框住，组内不画分隔线）
const selectedCol = ref(null)       // field_name
const selectedGroupId = ref(null)   // 编组 id
const selectedColNames = computed(() => {
  if (selectedCol.value) return [selectedCol.value]
  if (selectedGroupId.value == null) return []
  return headerTree.value.filter(n => n.isGroup && n.group.id === selectedGroupId.value)
    .flatMap(n => n.fields.map(f => f.field_name))
})
// 选中范围内的列：返回其需要画的左/右边框（整组只在首列画左边、末列画右边），不在范围内返回 null
function selEdges(fieldName) {
  const names = selectedColNames.value
  const i = fieldName ? names.indexOf(fieldName) : -1
  if (i < 0) return null
  return [...(i === 0 || isFrozen(names[i - 1]) !== isFrozen(fieldName) ? ['sel-l'] : []),
    ...(i === names.length - 1 || isFrozen(names[i + 1]) !== isFrozen(fieldName) ? ['sel-r'] : [])]
}
function clearColSelection() {
  if (!selectedCol.value && selectedGroupId.value == null) return
  selectedCol.value = null
  selectedGroupId.value = null
  gridRef.value?.refreshColumn?.()
}
function onHeaderClick({ column, $event }) {
  if (column.params?.addField) { emit('add-field', $event); return }
  if ($event?.target?.closest?.('.head-menu, .filter-dot, .cg-caret')) return
  const group = !column?.field && column?.params?.group
  if (!group && !props.fields.some(f => f.field_name === column?.field)) return
  selectedCell.value = null
  editingCell.value = null
  selectedCol.value = group ? null : column.field
  selectedGroupId.value = group ? group.id : null
  gridRef.value?.refreshColumn?.()
}
function onFooterClick({ column }) {
  if (column.params?.rowNumber && props.canCreate) emit('add-row')
}
function onHeaderDblClick({ column, $event }) {
  // 编组表头：双击打开「修改编组」
  const at = $event ? { x: $event.clientX, y: $event.clientY } : null   // 面板在双击位置弹出
  if (!column?.field && column?.params?.group) { emit('group-edit', column.params.group, at); return }
  if (!column?.field || $event?.target?.closest?.('.head-menu, .filter-dot')) return
  const f = props.fields.find(x => x.field_name === column.field)
  if (f) emit('field-edit', f, at)
}

// ---------- AI 生成按钮：选中 AI 列 → 浮在列头右侧；选中 AI 单元格 → 浮在单元格右侧 ----------
const aiBtn = ref(null)   // {x, y, mode, field, row}
function locateAiBtn() {
  aiBtn.value = null
  if (props.readonly) return
  if (selectedCol.value) {
    const f = props.fields.find(x => x.field_name === selectedCol.value)
    if (f?.field_type !== 'ai') return
    const th = [...document.querySelectorAll('.smart-vxe th.th-col-selected')].find(isDisplayCell)
    if (!th) return
    const r = th.getBoundingClientRect()
    aiBtn.value = { x: r.right + 6, y: r.top + 8, mode: 'col', field: f, row: null }
    return
  }
  const sc = selectedCell.value
  if (!sc) return
  const f = props.fields.find(x => x.field_name === sc.fieldName)
  if (f?.field_type !== 'ai') return
  const row = gridRows.value.find(r => r.__key === sc.key)
  const td = [...document.querySelectorAll('.smart-vxe td.cell-selected, .smart-vxe td.cell-selected-enum')].find(isDisplayCell)
  if (!td || !row) return
  const r = td.getBoundingClientRect()
  aiBtn.value = { x: r.right + 6, y: r.top + (r.height - 32) / 2, mode: 'cell', field: f, row }
}
let locateRaf = 0
function scheduleLocate() {
  cancelAnimationFrame(locateRaf)
  locateRaf = requestAnimationFrame(() => requestAnimationFrame(locateAiBtn))
}
// ---------- 展开记录按钮：hover 行优先，否则当前行（选中/编辑单元格所在行、详情打开的记录） ----------
const hoverKey = ref(null)
let expandHideTimer = 0
// 原生 mouseover 定位 hover 行（vxe 的 cell-mouseenter 只在配置了 tooltip 时才派发）
function onRowOver(e) {
  const tr = e.target.closest?.('tr.vxe-body--row')
  if (!tr) { scheduleExpandHide(); return }
  cancelExpandHide()
  const key = tr.getAttribute('rowid')
  const row = key && gridRows.value.find(r => r.__key === key)
  hoverKey.value = row && !row.__rowType ? key : null
}
// 离开行时延迟收起：鼠标从行移到骑在边框外侧的按钮上，中途会短暂离开表格
function scheduleExpandHide() {
  cancelExpandHide()
  expandHideTimer = setTimeout(() => { hoverKey.value = null }, 120)
}
function cancelExpandHide() { clearTimeout(expandHideTimer) }
const currentRowKey = computed(() => {
  const k = selectedCell.value?.key ?? editingCell.value?.key
  if (k) return k
  if (props.activeRowId == null) return null
  return gridRows.value.find(r => !r.__rowType && r.id === props.activeRowId)?.__key ?? null
})
const expandBtn = ref(null)   // {x, y, row}；只在 RowExpandBtn 内读取，勿在 SmartGrid 模板中直接引用
const RowExpandBtn = {
  name: 'RowExpandBtn',
  setup: () => () => {
    const b = expandBtn.value
    if (!b) return null
    return h(Teleport, { to: 'body' }, h('span', {
      class: 'st-row-expand', 'data-smart-tip': '展开记录',
      style: { left: `${b.x}px`, top: `${b.y}px` },
      onMouseenter: cancelExpandHide, onMouseleave: scheduleExpandHide,
      onMousedown: (e) => e.stopPropagation(),
      onClick: (e) => { e.stopPropagation(); emit('expand-row', b.row) },
    }, [h(StIcon, { name: 'expand', size: 12 })]))
  },
}
function locateExpandBtn() {
  const key = hoverKey.value || currentRowKey.value
  const row = key && gridRows.value.find(r => r.__key === key)
  const tableEl = gridRef.value?.$el
  if (!row || row.__rowType || !tableEl) { expandBtn.value = null; return }
  const td = [...tableEl.querySelectorAll(`.vxe-body--row[rowid="${key}"] > td`)].find(isDisplayCell)
  const r = visibleCellRect(td)
  if (!r) { expandBtn.value = null; return }
  const left = tableEl.getBoundingClientRect().left
  // 20px 按钮中心压在左边框；纵向上移 1px，保持光学居中。
  const x = Math.round(left - 10)
  const y = Math.round(r.top + r.height / 2 - 10 - 1)
  const cur = expandBtn.value
  if (cur && cur.x === x && cur.y === y && cur.row.__key === row.__key) return   // 位置未变（如横向滚动）不写响应式
  expandBtn.value = { x, y, row }
}
let expandRaf = 0
function scheduleExpandLocate() {
  cancelAnimationFrame(expandRaf)
  expandRaf = requestAnimationFrame(locateExpandBtn)
}

let rowSnapTimer = null
let scrollPointerDown = false
let locatingUntil = 0
let wheelRemainder = 0
let lastWheelTime = 0
function onGridWheel(event) {
  // 横向手势、缩放和编辑器内滚动仍由原控件处理。
  if (event.ctrlKey || event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)
      || !event.deltaY || !event.cancelable
      || !event.target.closest('.vxe-table--body-wrapper')
      || event.target.closest('input, textarea, [contenteditable="true"], .cell-editor, .el-popper')) return
  const table = gridRef.value
  const body = table?.$el?.querySelector('.body--wrapper > .vxe-table--body-inner-wrapper')
  if (!body || body.scrollHeight <= body.clientHeight) return
  event.preventDefault()
  event.stopPropagation()
  clearTimeout(rowSnapTimer)
  const now = Date.now()
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? body.clientHeight : 1)
  if (now - lastWheelTime > 180 || Math.sign(delta) !== Math.sign(wheelRemainder)) wheelRemainder = 0
  lastWheelTime = now
  wheelRemainder += delta
  const steps = Math.min(5, Math.floor(Math.abs(wheelRemainder) / 40))
  if (!steps) return
  const direction = Math.sign(wheelRemainder)
  wheelRemainder %= 40
  const top = body.scrollTop
  const viewportTop = body.getBoundingClientRect().top + body.clientTop
  const offsets = [...body.querySelectorAll('.vxe-body--row')]
    .map(row => top + row.getBoundingClientRect().top - viewportTop)
    .filter(offset => direction > 0 ? offset > top + .5 : offset < top - .5)
    .sort((a, b) => direction * (a - b))
  const target = offsets[Math.min(steps, offsets.length) - 1]
  if (target != null) table.scrollTo(undefined, Math.max(0, Math.min(target, body.scrollHeight - body.clientHeight)))
}
function scheduleRowSnap() {
  clearTimeout(rowSnapTimer)
  if (scrollPointerDown || Date.now() < locatingUntil) return
  rowSnapTimer = setTimeout(snapToRow, 160)
}
function snapToRow() {
  if (scrollPointerDown || Date.now() < locatingUntil) return
  const table = gridRef.value
  const body = table?.$el?.querySelector('.body--wrapper > .vxe-table--body-inner-wrapper')
  if (!body) return
  const top = body.scrollTop
  const max = body.scrollHeight - body.clientHeight
  // 保留首尾的自然边界，避免吸附导致最后一条记录无法完整看到。
  if (top <= 0 || top >= max - 1) return
  const viewportTop = body.getBoundingClientRect().top + body.clientTop
  const offsets = [...body.querySelectorAll('.vxe-body--row')]
    .map(row => top + row.getBoundingClientRect().top - viewportTop)
    .filter(offset => offset >= 0 && offset <= max)
  if (!offsets.length) return
  const target = offsets.reduce((best, offset) => Math.abs(offset - top) < Math.abs(best - top) ? offset : best)
  if (Math.abs(target - top) > .5) table.scrollTo(undefined, target)
}
function onScrollPointerDown(event) {
  if (gridRef.value?.$el?.contains(event.target)) {
    scrollPointerDown = true
    clearTimeout(rowSnapTimer)
  }
}
function onScrollPointerUp() {
  if (!scrollPointerDown) return
  scrollPointerDown = false
  scheduleRowSnap()
}
let lastScrollTop = 0
let lastScrollLeft = 0
function onGridScroll() {
  scheduleExpandLocate()
  if (blockedHint.value) hideBlockedHint()
  if (aiBtn.value || selectedCol.value || selectedCell.value) scheduleLocate()
  const scroll = gridRef.value?.getScroll?.() || {}
  const top = scroll.scrollTop ?? 0
  const left = scroll.scrollLeft ?? 0
  if ((top !== lastScrollTop || left !== lastScrollLeft) && editingCell.value) {
    const field = props.fields.find(f => f.field_name === editingCell.value.fieldName)
    if (typeOf(field) === 'date') {
      selectedCell.value = { ...editingCell.value }
      editingCell.value = null
    }
  }
  lastScrollLeft = left
  if (top !== lastScrollTop) {
    lastScrollTop = top
    scheduleRowSnap()
  }
}
function onAiBtnRun(scope) {
  const b = aiBtn.value
  if (!b) return
  if (scope === 'row' && b.row) emit('ai-run', b.field, 'rows', [b.row.id])
  else emit('ai-run', b.field, scope)
}

const isFrozen = (name) => headerTree.value.some(n => n.fixed === 'left'
  && (n.isGroup ? n.fields.some(f => f.field_name === name) : n.field.field_name === name))

// 行序列：折叠分组过滤 + 树形缩进标记 + 行号（添加一行入口在统计行左侧「＋」，不再虚拟数据行）；
// 每个展开组的末尾插一条 group-add 伪行（组内「+」添加，带全部分组条件预设）
const gridRows = computed(() => {
  const out = []
  let no = 0
  const hiddenUnder = []   // 折叠组的 key 前缀栈
  const idDepth = new Map()   // 树形：记录 id → 深度
  const stack = []   // 可见展开组栈：{key, depth, conds:[{fieldId, value}]}
  const closeTo = (depth) => {
    while (stack.length && stack[stack.length - 1].depth >= depth) {
      const g = stack.pop()
      out.push({ __rowType: 'group-add', __key: `ga_${g.key}`, conds: g.conds, depth: g.depth })
    }
  }
  for (const r of props.rows) {
    if (r.__rowType === 'group') {
      closeTo(r.depth)
      while (hiddenUnder.length && r.depth <= hiddenUnder[hiddenUnder.length - 1].depth) hiddenUnder.pop()
      if (hiddenUnder.length) continue
      out.push({ ...r, __key: r.key })
      if (props.collapsedGroups.has(r.key)) {
        hiddenUnder.push(r)   // 折叠组自身可见，但其数据行与组内「+」行都隐去（不入栈）
      } else {
        const parentConds = stack.length ? stack[stack.length - 1].conds : []
        stack.push({ key: r.key, depth: r.depth, conds: [...parentConds, { fieldId: r.fieldId, value: r.value }] })
      }
      continue
    }
    if (hiddenUnder.length) continue
    no += 1
    let depth = 0
    if (r.parent_id != null) depth = (idDepth.get(r.parent_id) ?? 0) + 1
    idDepth.set(r.id, depth)
    out.push({ ...r, __key: `r_${r.id}`, __no: no, __indent: depth })
  }
  closeTo(-1)
  return out
})

// 树形子记录计数（父行首列的徽标：树形图标 + 子记录数）
const childCounts = computed(() => {
  const m = new Map()
  for (const r of props.rows) {
    if (!r.__rowType && r.parent_id != null) m.set(r.parent_id, (m.get(r.parent_id) || 0) + 1)
  }
  return m
})

// 最后一条数据行：紧贴表体底边，分数缩放（125% 等）下选中框底边会被取整裁掉，单独加粗底边
const lastRowKey = computed(() => {
  for (let i = gridRows.value.length - 1; i >= 0; i--) if (!gridRows.value[i].__rowType) return gridRows.value[i].__key
  return null
})
const rowClass = ({ row }) => {
  if (row.__rowType === 'group') return `row-group depth-${row.depth}`
  if (row.__rowType === 'group-add') return `row-group-add depth-${row.depth}`
  const cls = []
  if (row.__key === lastRowKey.value) cls.push('row-last')
  // 当前行：单击/双击行内单元格（选中/编辑态）或详情面板打开的记录 → 展开按钮常显
  const cur = selectedCell.value?.key ?? editingCell.value?.key
  if (row.__key === cur) cls.push('row-current')
  if (props.activeRowId != null && row.id === props.activeRowId) cls.push('row-current', 'row-active')
  return cls.join(' ')
}

// 整行填色：数据行 __key → 命中色（规则勾了 wholeRow 且条件命中）
const rowFills = computed(() => {
  const m = new Map()
  const rules = fillRules.value || []
  if (!rules.some(r => r.wholeRow)) return m
  for (const r of gridRows.value) {
    if (r.__rowType) continue
    const c = evalRowFill(rules, props.fields, r)
    if (c) m.set(r.__key, c)
  }
  return m
})

const searchMatchKeys = computed(() => findMatchKeys(props.searchMatches))
const searchRowIds = computed(() => new Set(props.searchMatches.map(m => m.recordId)))
const searchActiveKey = computed(() => currentFindKey(props.searchMatches, props.searchCurrentIndex))
watch([searchMatchKeys, searchActiveKey], () => gridRef.value?.refreshColumn?.())

function cellClass({ row, column }) {
  const cls = []
  if (!row.__rowType) {
    const key = findCellKey(row.id, column.field)
    if (searchMatchKeys.value.has(key)) cls.push('cell-search-match')
    if (column.params?.rowNumber && searchRowIds.value.has(row.id)) cls.push('cell-search-match')
    if (searchActiveKey.value === key) cls.push('cell-search-active')
  }
  if (!row.__rowType && row.__indent > 0 && column.field === visibleFields.value[0]?.field_name) {
    cls.push('cell-indent')
  }
  // 单击选中态（企微式：边框与单元格同大，与编辑态边框同款）。
  if (!row.__rowType && ['image', 'url', 'relation'].includes(typeOf(props.fields.find(f => f.field_name === column.field)))) cls.push('cell-image')
  // 单选/多选用独立类名：选中框由锚点自绘（标签换行展开时随内容增高），不走 td inset 阴影
  if (selectedCell.value && row.__key === selectedCell.value.key && column.field === selectedCell.value.fieldName) {
    const f = props.fields.find(x => x.field_name === column.field)
    cls.push(['singleSelect', 'multiSelect', 'file', 'relation'].includes(typeOf(f)) ? 'cell-selected-enum' : 'cell-selected')
  }
  // 编辑态：去单元格内边距，编辑器与单元格严格同边界。
  // 单选/多选追加 cell-editing-enum：锚点换行展开（同选中态），边框由锚点自绘
  if (editingCell.value && row.__key === editingCell.value.key && column.field === editingCell.value.fieldName) {
    const f = props.fields.find(x => x.field_name === column.field)
    if (!['image', 'file', 'url', 'relation'].includes(typeOf(f))) cls.push('cell-editing')
    if (['singleSelect', 'multiSelect'].includes(typeOf(f))) cls.push('cell-editing-enum')
  }
  const edge = selEdges(column.field)
  if (edge) cls.push('col-selected', ...edge)
  return cls.join(' ')
}

// AI 字段的「有效字段」：按输出类型渲染/编辑（单选/多选同普通选项字段），提交仍按原字段
const effCache = new WeakMap()
function effOf(field) {
  if (field?.field_type !== 'ai') return field
  let e = effCache.get(field)
  if (!e) { e = { ...field, field_type: field.options?.outputType || 'text', __aiField: true }; effCache.set(field, e) }
  return e
}
const typeOf = (field) => effOf(field)?.field_type

function canEdit(row, field) {
  if (props.readonly) return false
  return props.canEditCell ? props.canEditCell(row, field) : true
}

// 单元格渲染（含填色命中 + 编辑态分发）
function CellSlot(props2) {
  const { row, field } = props2
  const firstField = visibleFields.value[0]?.field_name
  // 组内「+」行：仅首字段列可点（带上该组全部条件预设添加记录）
  if (row.__rowType === 'group-add') {
    if (field.field_name !== firstField || props.readonly) return h('span')
    return h('span', {
      class: 'group-add-btn', 'data-smart-tip': '在该组内添加一行',
      onClick: (e) => { e.stopPropagation(); emit('add-row-in-group', row.conds) },
    }, [h(StIcon, { name: 'plus', size: 13 })])
  }
  if (row.__rowType === 'group') {
    if (field.field_name !== firstField) {
      const agg = row.aggs?.[field.field_name]
      const aggKind = viewConfig.value.aggregations?.[field.field_name]
      // 聚合值带 ⌄：点击切换统计方式（复用统计行菜单）
      return h('span', {
        class: 'group-agg', 'data-smart-tip': '点击设置统计方式',
        onClick: (e) => { e.stopPropagation(); emit('footer-menu', field, e) },
      }, agg != null && aggKind
        ? [`${STAT_LABELS[aggKind] || ''} ${formatStatValue(aggKind, agg, field)}`, h(CellDropdown, { class: 'ga-caret', decorative: true })]
        : '')
    }
    return h('span', { class: 'group-head' }, [
      ...groupValueNodes(row),
      h('span', { class: 'g-count' }, `记录数 ${row.count}`),
    ])
  }
  const ef = effOf(field)
  // 图片始终复用同一个锚点，选中/展开时不替换缩略图 DOM，避免尺寸和位置抖动。
  if (['image', 'file', 'url', 'relation'].includes(ef.field_type)) {
    const cell = { key: row.__key, fieldName: field.field_name }
    const isCurrent = value => value?.key === cell.key && value?.fieldName === cell.fieldName
    return h(ef.field_type === 'image' ? ImageCellPanel : ef.field_type === 'file' ? FileCellPanel : ef.field_type === 'relation' ? RelationCellPanel : LinkCellPanel, {
      field: ef, record: row,
      style: { '--file-row-height': `${rowHeightPx.value}px` },
      value: row[field.field_name], readonly: !canEdit(row, field) || props.readonly,
      selected: isCurrent(selectedCell.value),
      initialInput: isCurrent(editingCell.value) ? editingCell.value.initialInput : undefined,
      advanceOnEnter: true,
      onAdvance: direction => advanceCell(row, field, direction),
      onSelect: () => { clearColSelection(); selectedCell.value = cell },
      onOpen: () => { editingCell.value = cell },
      onCollapse: () => { if (isCurrent(editingCell.value)) editingCell.value = null; selectedCell.value = cell },
      onCancel: () => { if (isCurrent(editingCell.value)) editingCell.value = null },
      onCommit: value => emit('cell-commit', { row, field, value }),
    })
  }
  const isEdit = editingCell.value && editingCell.value.key === row.__key && editingCell.value.fieldName === field.field_name
  if (isEdit && canEdit(row, field)) {
    return h(SmartCellEditor, {
      field: ef, record: row,
      initialInput: editingCell.value.initialInput,
      advanceOnEnter: true,
      onAdvance: direction => advanceCell(row, field, direction),
      frozen: isFrozen(field.field_name),   // 编辑器按 wrapper 判断自己是不是显示副本用
      onCommit: (v) => { editingCell.value = null; emit('cell-commit', { row, field, value: v }) },
      onCancel: () => { editingCell.value = null },
      // 枚举收起面板：草稿软提交（不关编辑器、未改不写库）后回到选中态，而非取消选中
      'onCommit-soft': (v) => emit('cell-commit', { row, field, value: v }),
      onCollapse: () => {
        editingCell.value = null
        selectedCell.value = { key: row.__key, fieldName: field.field_name }
      },
      'onOpen-config': (f) => emit('open-config', f),
      // 单元格内新建选项：父级落库为真选项后提交新 optionId（编辑器即关闭）
      'onAdd-option': (label) => { editingCell.value = null; emit('add-option', { row, field, label }) },
    })
  }
  // 单选/多选单击选中：呈现编辑态锚点（标签+✕+下拉按钮），面板不展开；
  if (ef.field_type === 'progress' && canEdit(row, field) && selectedCell.value?.key === row.__key
      && selectedCell.value?.fieldName === field.field_name) {
    return h(ProgressCell, {
      value: row[field.field_name], config: ef.options || {}, interactive: true,
      onPointerdown: event => {
        // 首击会替换 DOM，原生 dblclick 可能丢失；在第二击改变滑块值之前切到数字编辑。
        if (lastClick.key === row.__key && lastClick.fieldName === field.field_name && Date.now() - lastClick.t < 400) {
          event.preventDefault()
          event.stopPropagation()
          lastClick = { key: null, fieldName: null, t: 0 }
          selectedCell.value = null
          editingCell.value = { key: row.__key, fieldName: field.field_name }
        }
      },
      onCommit: value => emit('cell-commit', { row, field, value }),
      onCancel: () => { selectedCell.value = null },
      'onEnter-edit': () => {
        selectedCell.value = null
        editingCell.value = { key: row.__key, fieldName: field.field_name }
      },
    })
  }
  // 点下拉按钮或双击锚点 → open 进编辑态（面板展开）
  const isSelEnum = selectedCell.value && selectedCell.value.key === row.__key
    && selectedCell.value.fieldName === field.field_name
    && ['singleSelect', 'multiSelect'].includes(ef.field_type)
  if (isSelEnum) {
    return h(SelectCellPanel, {
      field: ef, record: row, frozen: isFrozen(field.field_name), closed: true,
      onCommit: (v) => emit('cell-commit', { row, field, value: v }),   // ✕ 清除直接生效
      onOpen: () => {
        if (!canEdit(row, field)) return
        selectedCell.value = null
        editingCell.value = { key: row.__key, fieldName: field.field_name }
      },
    })
  }
  // 未进入编辑时继续展示原内容，键入后的首段文本由输入缓冲交给编辑器。
  // 填色只在 td 级铺满（cellFillStyle）；不再给 SmartCell 内容层重复着色——内容层色块只盖住文字范围，
  // 选中列/悬停等改变 td 底色时会露出一块块残色
  const cell = h(SmartCell, { field, record: row })
  // 树形父行：首字段列前置子记录计数徽标（树形图标 + N）
  const childN = field.field_name === firstField ? childCounts.value.get(row.id) : 0
  if (childN) {
    return h('span', { class: 'tree-cell' }, [
      h('span', { class: 'tree-badge', 'data-smart-tip': `${childN} 条子记录` }, [h(StIcon, { name: 'tree', size: 11 }), String(childN)]),
      cell,
    ])
  }
  return cell
}

// 分组头的分组值：枚举 → 彩色 chip；空 → 灰字「字段: 空」；其余 → 文本
function groupValueNodes(row) {
  const f = props.fields.find(x => x.field_name === row.fieldId)
  const v = row.value
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) {
    return [h('span', { class: 'gv-empty' }, `${f?.label || ''}: 空`)]
  }
  if (f?.field_type === 'singleSelect' || f?.field_type === 'multiSelect') {
    const opts = f.options?.options || []
    const ids = Array.isArray(v) ? v : [v]
    return ids.map(id => {
      const o = opts.find(x => x.id === id)
      return h('span', {
        class: 'gv-chip',
        style: { background: optionColor(o?.color).value, color: optionColor(o?.color).text },
      }, o?.label ?? id)
    })
  }
  return [h('span', { class: 'gv-text' }, `${f?.label}: ${v}`)]
}

// 填色在 td 级着底色（整格铺满，企微式）
function cellFillStyle({ row, column }) {
  if (!row || row.__rowType) return null
  if (searchMatchKeys.value.has(findCellKey(row.id, column.field))
      || (column.params?.rowNumber && searchRowIds.value.has(row.id))) return { backgroundColor: '#FFFCEB', '--st-cell-fill': '#FFFCEB' }
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return null
  const fill = evalFillRules(fillRules.value, f, row[f.field_name]) || rowFills.value.get(row.__key) || null
  return fill ? { backgroundColor: fill, '--st-cell-fill': fill } : null
}

// 整列填色之「为字段名称填色」：表头单元格着底色
function headerCellStyle({ column }) {
  const color = headerFillColor(fillRules.value, column.field)
  return color ? { backgroundColor: color } : null
}

// 统计行单元格（设计稿 PixPin_2026-10-15_19-57-43）：已配置列两行布局——上行小灰字统计方式名、
// 下行数值（右对齐）；未配置列默认空白，hover 浮现「统计 ▾」提示可点击。点击出统计方式菜单。
// 未配置时首字段列默认「记录数 N」，与已配置列同款两行样式
function FooterCell({ field }) {
  const aggKind = viewConfig.value.aggregations?.[field.field_name]
  const val = props.aggregations[field.field_name]
  const isFirst = field.field_name === visibleFields.value[0]?.field_name
  const label = aggKind ? (STAT_LABELS[aggKind] || '') : (isFirst ? '记录数' : '')
  const children = []
  if (label) {
    const value = aggKind ? (val != null ? formatStatValue(aggKind, val, field) : '-') : props.total
    children.push(
      h('div', { class: 'fs-label' }, label),
      h('div', { class: 'fs-value' }, String(value)),
    )
  } else {
    children.push(h('div', { class: 'fs-hint' }, ['统计', h(CellDropdown, { class: 'fs-caret', decorative: true })]))
  }
  return h('div', {
    class: 'footer-stat', 'data-smart-tip': '点击设置统计方式',
    onClick: (e) => { e.stopPropagation(); emit('footer-menu', field, e) },
  }, children)
}

// vxe 的 footer 行数由 footer-method 决定：返回一行占位（内容由各列 #footer 插槽渲染），
// 没有它 footerTableData 为空，整个统计栏不会渲染
function footerMethod({ columns }) {
  return [columns.map(() => '')]
}

const IMMEDIATE = ['checkbox']
const selectedCell = ref(null)   // 单击选中态 {key, fieldName}（企微式：单击选中、双击编辑）
const typingBuffer = ref(null)
let typingComposing = false
watch(selectedCell, async cell => {
  if (!cell) return
  await nextTick()
  if (selectedCell.value !== cell || editingCell.value) return
  typingBuffer.value.value = ''
  typingBuffer.value.focus({ preventScroll: true })
})
function finishSelectedComposition(event) {
  typingComposing = false
  onSelectedInput(event)
}
function onSelectedInput(event) {
  if (typingComposing || event.isComposing) return
  const text = event.target.value
  event.target.value = ''
  if (!text) return
  if (editingCell.value?.initialInput != null) {
    editingCell.value = { ...editingCell.value, initialInput: editingCell.value.initialInput + text }
    return
  }
  const cell = selectedCell.value
  if (!cell) return
  const row = gridRows.value.find(r => r.__key === cell.key)
  const field = props.fields.find(f => f.field_name === cell.fieldName)
  if (!row || !field || !canEdit(row, field)) return
  if (!['inline', 'progress', 'date', 'select', 'member', 'url'].includes(regOf(effOf(field)).editor)) return
  editingCell.value = { ...cell, initialInput: text }
  if (typeOf(field) !== 'url') selectedCell.value = null
}
async function advanceCell(row, field, direction = 'down') {
  await moveCell(direction, { key: row.__key, fieldName: field.field_name })
}
let navigationVersion = 0
async function moveCell(direction, current = selectedCell.value) {
  const target = nextCell(gridRows.value, displayedFields.value, current, direction)
  if (!target) return
  const version = ++navigationVersion
  editingCell.value = null
  clearColSelection()
  selectedCell.value = target
  await nextTick()
  if (version !== navigationVersion) return
  const row = gridRows.value.find(r => r.__key === target.key)
  const column = gridRef.value?.getColumnByField?.(target.fieldName)
  await gridRef.value?.scrollToRow?.(row)
  if (version !== navigationVersion) return
  if (column) await gridRef.value?.scrollToColumn?.(column)
}
watch([selectedCol, selectedCell, () => props.rows], scheduleLocate)   // 选中 AI 列/单元格（或数据刷新）→ 重新定位生成按钮
// 展开记录按钮跟随 hover 行 / 当前行 / 数据与行高变化（须在 selectedCell 声明之后：watch 立即求值）
watch([hoverKey, currentRowKey, () => props.rows, () => props.view?.config?.rowHeight], scheduleExpandLocate)
let lastClick = { key: null, fieldName: null, t: 0 }   // 自检测双击用

function onCellClick({ row, column }) {
  if (props.readonly) return
  if (!row || row.__rowType) return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return
  // 切换目标时结束旧编辑态；新选中必须在同一次 click 中落下。
  if (editingCell.value && (editingCell.value.key !== row.__key || editingCell.value.fieldName !== f.field_name)) {
    editingCell.value = null
  }
  clearColSelection()
  if (IMMEDIATE.includes(typeOf(f))) {
    if (!canEdit(row, f)) return
    emit('cell-commit', { row, field: f, value: !row[f.field_name] })
    return
  }
  // 自检测双击：同一单元格 400ms 内的第二击直接进编辑。原生 dblclick 不可靠——
  // 第一击后选中态锚点/预览浮层会替换单元格 DOM，两次点击落在不同元素上时 Chrome 不合成 dblclick
  const now = Date.now()
  const isSecond = lastClick.key === row.__key && lastClick.fieldName === f.field_name && now - lastClick.t < 400
  lastClick = isSecond ? { key: null, fieldName: null, t: 0 } : { key: row.__key, fieldName: f.field_name, t: now }
  if (isSecond) {
    if (!canEdit(row, f)) { showBlockedHint(row, f); return }
    selectedCell.value = null
    editingCell.value = { key: row.__key, fieldName: f.field_name }
    return
  }
  // 只读字段保持选中，可通过后续操作查看权限或类型提示。
  selectedCell.value = { key: row.__key, fieldName: f.field_name }
}

function onCellDblClick({ row, column }) {
  if (!row || row.__rowType) return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return
  // 附件组件自己处理单击、预览及面板开关；快速连点箭头产生的 dblclick
  // 不应再进入通用编辑流程，否则会清掉组件仍在使用的选中状态。
  if (['image', 'file', 'url', 'relation'].includes(typeOf(f))) return
  if (props.readonly) { showBlockedHint(row, f); return }
  if (IMMEDIATE.includes(typeOf(f))) return   // checkbox 单击已切换，无需编辑态
  if (!canEdit(row, f)) { showBlockedHint(row, f); return }
  selectedCell.value = null   // 编辑态即脱离选中态
  editingCell.value = { key: row.__key, fieldName: f.field_name }
}

// ---------- 不可编辑提示：公式/查找引用/自动编号/系统字段 → 「X不可直接编辑 · 修改设置」；无权限 → 权限提示 ----------
const BLOCKED_TEXT = BLOCKED_EDIT_TEXT
const CONFIGURABLE = BLOCKED_CONFIGURABLE
const blockedHint = ref(null)   // {x, y, text, field}
function showBlockedHint(row, f) {
  const ft = typeOf(f)
  const typeText = BLOCKED_TEXT[ft]
  const text = typeText || (props.readonly ? '你没有编辑该表格的权限' : '你没有编辑该单元格的权限')
  selectedCell.value = { key: row.__key, fieldName: f.field_name }   // 保持选中框
  nextTick(() => requestAnimationFrame(() => {
    const td = [...document.querySelectorAll('.smart-vxe td.cell-selected, .smart-vxe td.cell-selected-enum')].find(isDisplayCell)
    if (!td) return
    const r = td.getBoundingClientRect()
    const x = Math.max(8, Math.min(r.left, window.innerWidth - 280))
    const y = r.bottom + 260 > window.innerHeight ? r.top - 46 : r.bottom + 6   // 下方放不下就放上方
    blockedHint.value = { x, y, text, field: typeText && CONFIGURABLE.includes(ft) && !props.readonly ? f : null }
    setTimeout(() => document.addEventListener('mousedown', onHintOutside, true), 0)
  }))
}
// 点提示气泡以外 → 关闭（气泡内的「修改设置」要能点到，不能在 mousedown 阶段就把气泡移除）
function onHintOutside(e) {
  if (e.target.closest?.('.st-blocked-hint')) return
  hideBlockedHint()
}
function hideBlockedHint() {
  blockedHint.value = null
  document.removeEventListener('mousedown', onHintOutside, true)
}
function openBlockedConfig() {
  const f = blockedHint.value?.field
  hideBlockedHint()
  if (f) emit('open-config', f)
}
watch(selectedCell, (v) => { if (!v) hideBlockedHint() })

// Esc 取消选中（编辑态的 Esc 由编辑器自身处理）
function onDocKeydown(e) {
  // 只接管当前网格的选中态，避免抢走搜索框、弹窗和编辑器的键盘事件。
  if (e.target !== typingBuffer.value || e.isComposing || typingComposing || e.keyCode === 229) return
  if (!editingCell.value && selectedCell.value && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const direction = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: e.shiftKey ? 'up' : 'down', Tab: e.shiftKey ? 'left' : 'right' }[e.key]
    if (direction) {
      e.preventDefault(); e.stopPropagation()
      moveCell(direction)
      return
    }
  }
  if (e.key === 'Escape' && selectedCell.value && !editingCell.value) {
    selectedCell.value = null
    // vxe 的 cell-class-name 只在渲染周期重算：Esc 清选中不走数据流，手动触发列重渲染
    gridRef.value?.refreshColumn?.()
  }
}

// 表格内部切换交给 cell-click 原子地更新选中。不能在 mousedown 时 refreshColumn：
// 它会重建鼠标下的目标 DOM，导致 mouseup/click 丢失，用户被迫再点一次。
function onDocMouseDown(e) {
  if (e.target.closest?.('.el-image-viewer__wrapper')) return
  const cell = e.target.closest?.('td, th')
  if (cell && gridRef.value?.$el?.contains(cell)) return
  if ((selectedCol.value || selectedGroupId.value != null) && !e.target.closest?.('th.th-col-selected, .arb')) clearColSelection()
  if (!selectedCell.value || editingCell.value) return
  if (e.target.closest?.('.arb')) return   // AI 生成按钮（浮在单元格右侧）
  if (e.target.closest?.('td.cell-selected, td.cell-selected-enum')) return
  if (e.target.closest?.('.cell-overlay')) return   // 文本预览浮层 teleport 在 body，它自己管外部关闭
  selectedCell.value = null
  gridRef.value?.refreshColumn?.()
}

// 通过 vxe 菜单钩子获取行列上下文，使用独立浮层统一菜单样式。
const cellMenu = ref(null)
const menuConfig = computed(() => ({
  body: { options: [[{ code: 'expand', name: 'expand' }]] },
  visibleMethod: ({ row, column, $event, type }) => {
    cellMenu.value = null
    if (type !== 'body' || !row || row.__rowType) return false
    const field = props.fields.find(f => f.field_name === column?.field)
    if (field) {
      clearColSelection()
      selectedCell.value = { key: row.__key, fieldName: field.field_name }
    }
    cellMenu.value = { row, field, x: $event.clientX, y: $event.clientY }
    return false
  },
}))
function onMenuAction(cmd, count) {
  if (cellMenu.value) emit('cell-menu', { row: cellMenu.value.row, field: cellMenu.value.field, cmd, count })
}

function onCheckAll({ checked }) { emit('selection-change', checked ? dataRowSelection() : []) }
function onCheckChange() { emit('selection-change', dataRowSelection()) }
function dataRowSelection() {
  const recs = gridRef.value?.getCheckboxRecords?.() || []
  return recs.filter(r => !r.__rowType)
}

function attachGlobalEvents() {
  window.addEventListener('resize', scheduleLocate)
  window.addEventListener('resize', scheduleExpandLocate)
  document.addEventListener('keydown', onDocKeydown)
  document.addEventListener('pointerdown', onScrollPointerDown, true)
  document.addEventListener('pointerup', onScrollPointerUp, true)
  document.addEventListener('pointercancel', onScrollPointerUp, true)
  document.addEventListener('mousedown', onDocMouseDown)
}
function detachGlobalEvents() {
  clearTimeout(rowSnapTimer)
  document.removeEventListener('pointerdown', onScrollPointerDown, true)
  document.removeEventListener('pointerup', onScrollPointerUp, true)
  document.removeEventListener('pointercancel', onScrollPointerUp, true)
  window.removeEventListener('resize', scheduleExpandLocate)
  cancelExpandHide()
  document.removeEventListener('mousedown', onHintOutside, true)
  window.removeEventListener('resize', scheduleLocate)
  document.removeEventListener('keydown', onDocKeydown)
  document.removeEventListener('mousedown', onDocMouseDown)
}
onMounted(attachGlobalEvents)
onActivated(() => { attachGlobalEvents(); scheduleLocate(); scheduleExpandLocate() })
onDeactivated(() => { detachGlobalEvents(); editingCell.value = null })
onBeforeUnmount(detachGlobalEvents)

// 定位到指定记录：新增行默认选中首个可见列；查找定位可指定字段且只滚动、不弹出选中/编辑浮层。
// 记录不在当前行序列（被筛选掉 / 在折叠分组里）时返回 false；隐藏字段退化为只定位记录。
async function focusRecord(id, fieldName = null, { select = true, edit = false } = {}) {
  clearTimeout(rowSnapTimer)
  locatingUntil = Date.now() + 600
  await nextTick()   // 等 rows → gridRows → vxe data 刷新
  const row = gridRows.value.find(r => !r.__rowType && r.id === id)
  if (!row) return false
  const f = fieldName
    ? visibleFields.value.find(x => x.field_name === fieldName)
    : visibleFields.value[0]
  clearColSelection()
  editingCell.value = null
  if (select) {
    const target = f || visibleFields.value[0]
    if (target) selectedCell.value = { key: row.__key, fieldName: target.field_name }
  } else {
    selectedCell.value = null
  }
  const col = f ? gridRef.value?.getColumnByField?.(f.field_name) : null
  await gridRef.value?.refreshColumn?.()
  await gridRef.value?.scrollToRow?.(row)
  // 等行和虚拟列布局稳定后横向定位，避免重绘恢复旧滚动位置。
  await nextTick()
  if (col) await gridRef.value?.scrollToColumn?.(col, { colAlign: true })
  // 布局与滚动完成后挂载编辑器，由编辑器自动聚焦输入控件。
  // 首列为只读字段或复选框时保留选中态，不修改其值。
  if (edit && f && !props.readonly && canEdit(row, f) && !IMMEDIATE.includes(typeOf(f))) {
    selectedCell.value = null
    editingCell.value = { key: row.__key, fieldName: f.field_name }
    await nextTick()
  }
  return true
}

function orderSearchMatches(matches) {
  return orderFindMatches(matches, gridRows.value, displayedFields.value)
}

defineExpose({
  isEditing: () => !!editingCell.value || (document.activeElement?.matches?.('.progress-slider')
    && gridRef.value?.$el?.contains(document.activeElement)),
  orderSearchMatches,
  clearEditing: () => { editingCell.value = null; selectedCell.value = null; selectedCol.value = null; selectedGroupId.value = null },
  clearSelection: () => gridRef.value?.clearCheckboxRow?.(),
  focusRecord,
})
</script>

<style scoped>
.grid-typing-buffer { position: fixed; left: -100px; top: 0; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.smart-grid { width: 100%; }
.add-col { display: block; width: 100%; text-align: center; color: var(--st-text-3); font-weight: 600; cursor: pointer; font-size: 15px; }
/* 末尾添加列：浅灰底方块 + 灰「＋」（对齐参照 添加一列-按钮.png） */
/* 末尾「+」列与列外空白区：白底（vxe 表头容器默认灰底，列不满宽时右侧会露出灰条） */
.smart-vxe :deep(.vxe-table--header-wrapper),
.smart-vxe :deep(.vxe-table--header-inner-wrapper),
.smart-vxe :deep(.vxe-table--footer-wrapper) { background-color: #fff; }
/* 统计行左侧的添加一行「＋」：单元格内居中、整格可点、hover 主色 */
.footer-add-btn {
  display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;
  cursor: pointer; color: var(--el-text-color-regular); font-size: 16px; user-select: none;
}
.smart-vxe :deep(.vxe-header--column.th-add-col),
.smart-vxe :deep(.vxe-footer--column.footer-add-cell) { cursor: pointer; }
.smart-vxe :deep(.vxe-header--column.th-add-col:hover),
.smart-vxe :deep(.vxe-footer--column.footer-add-cell:hover) { background-color: var(--st-icon-hover-bg, #E6E8E8); }
.group-toggle { cursor: pointer; color: var(--el-text-color-secondary); user-select: none; }
.row-no { color: var(--el-text-color-placeholder); font-size: 12px; }
/* 详情面板打开的记录：整行浅灰底（参照 hover-行.png） */
.smart-vxe :deep(.vxe-body--row.row-active) { background-color: #F2F3F5; }
/* 填色单元格在原色上叠加浅灰，让整行 hover 连续；不占用选中框的伪元素或边线背景。 */
.smart-vxe :deep(.vxe-body--row.row--hover > .vxe-body--column[style*="--st-cell-fill"]) {
  background-color: color-mix(in srgb, var(--st-cell-fill) 94%, #30343b 6%) !important;
}
.group-head { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
/* 分组头：分组值彩色 chip（枚举）+ 记录数灰字（对齐参照 分组-1个字段.png） */
.gv-chip { border-radius: 4px; padding: 1px 8px; font-size: 12px; font-weight: 500; }
.gv-text { font-weight: 600; }
.gv-empty { color: var(--st-text-3); font-weight: 400; }
.g-count { font-size: 12px; color: var(--st-text-3); font-weight: 400; }
.group-agg { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: var(--el-text-color-secondary); cursor: pointer; }
.group-agg:hover .st-dd { background: #E6E8E8; }

/* 组内「+」行：灰色加号（对齐参照 分组-1个字段.png 每组末尾的 + 行） */
.smart-vxe :deep(.row-group-add) { background: #fff; }
.smart-vxe :deep(.row-group-add:hover) { background: var(--st-bg-hover); }
:deep(.group-add-btn) {
  display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border-radius: 4px; cursor: pointer; color: var(--st-text-3);
}
:deep(.group-add-btn:hover) { background: var(--st-bg-active); color: var(--st-primary); }
/* 树形父行：子记录计数徽标（树形图标 + N，对齐参照 单元格右键菜单-添加子记录.png） */
:deep(.tree-cell) { display: inline-flex; align-items: center; gap: 4px; width: 100%; }
:deep(.tree-badge) {
  display: inline-flex; align-items: center; gap: 2px; flex: none;
  font-size: 11px; color: var(--st-text-3);
}
/* 树形子行：浅灰虚线层级缩进线（替代纯 padding 缩进） */
.smart-vxe :deep(.cell-indent .vxe-cell) { border-left: 1px dashed var(--st-border); margin-left: 8px; padding-left: 10px; }
.smart-vxe :deep(.row-group) { background: var(--st-bg-canvas); }
.smart-vxe :deep(.row-group.depth-1) { background: #fafbfc; }
.smart-vxe :deep(.row-group.depth-2) { background: #fcfdfe; }
.smart-vxe :deep(.vxe-body--column.col-no) { color: var(--el-text-color-placeholder); font-size: 18px; }
/* 序号列：左右内边距对称、内容水平居中（vxe 默认左侧 padding 大于右侧，数字会偏） */
.smart-vxe :deep(.col-no .vxe-cell) { padding-left: 0 !important; padding-right: 0 !important; justify-content: center; text-align: center; }
.smart-vxe :deep(.col-no .vxe-cell--wrapper) { justify-content: center; width: 100%; }
.smart-vxe :deep(.col-no .vxe-cell--title) { text-align: center; }
/* 单击选中态：白底 + 2px 主色边框（inset 阴影实现，与单元格同大、不占布局）。
   所有字段类型统一：与文本预览浮层 / 枚举锚点 / 编辑态同一颜色、同一底色 */
.smart-vxe :deep(.vxe-body--column.cell-selected) {
  box-shadow: 0 0 0 2px var(--st-primary) inset; position: relative; z-index: 1;
}
/* 最后一行：单元格底边与表体可视区底边重合，分数缩放（125%/150%）取整会把贴边的边框裁掉一半
   （参照 PixPin_2026-10-17_16-27-20）。改为用覆盖层画框、底边离开单元格底边 2px，不再贴边 */
.smart-vxe :deep(.row-last .vxe-body--column.cell-selected),
.smart-vxe :deep(.row-last .vxe-body--column.cell-editing .vxe-cell) { box-shadow: none; }
.smart-vxe :deep(.row-last .vxe-body--column.cell-selected)::after,
.smart-vxe :deep(.row-last .vxe-body--column.cell-editing)::after {
  content: ''; position: absolute; left: 0; right: 0; top: 0; bottom: 2px; z-index: 6;
  border: 2px solid var(--st-primary); box-sizing: border-box; pointer-events: none; }
.smart-vxe :deep(.row-last .vxe-body--column.cell-editing) { position: relative; }
.smart-vxe :deep(.row-last .vxe-body--column.cell-editing-enum)::after { display: none; }   /* 枚举编辑态边框由锚点自绘 */
.smart-vxe :deep(.row-last .sel-anchor) { min-height: calc(100% - 2px); margin-bottom: 2px; }
/* 行高变大（参照 PixPin_2026-10-17_16-45-05）：内容从上方开始；文本先换行，放不下的最后一行再省略。
   上内边距 7px + 全局 -2px 光学上移 = 首行与默认行高时的位置一致 */
.smart-vxe.rh-tall :deep(.vxe-body--column) { vertical-align: top; }
.smart-vxe.rh-tall :deep(.vxe-body--column .vxe-cell) { align-items: flex-start; padding-top: 7px; padding-bottom: 4px; }
.smart-vxe.rh-tall :deep(.vxe-body--column .vxe-cell--wrapper) { align-items: flex-start; margin-top: 0 !important; margin-bottom: 0 !important; }   /* vxe 用内联 margin-top 做垂直居中，顶对齐时清掉 */
.smart-vxe.rh-tall :deep(.vxe-body--column .smart-cell) { align-items: flex-start; }
.smart-vxe.rh-tall :deep(.vxe-body--column .smart-cell .txt) {
  white-space: normal; word-break: break-all; line-height: 22px;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: var(--rh-lines); }
/* 序号、勾选框也顶对齐 */
.smart-vxe.rh-tall :deep(.vxe-body--column.col-ck .vxe-cell),
.smart-vxe.rh-tall :deep(.vxe-body--column.col-ck .vxe-cell--wrapper) { align-items: flex-start; height: auto; }
.smart-vxe.rh-tall :deep(.vxe-body--column.col-ck .vxe-cell) { padding-top: 10px; }
/* 单选/多选选中锚点：标签从上方开始（▼ 本就钉在右上角） */
.smart-vxe.rh-tall :deep(.sel-anchor) { align-content: flex-start; align-items: flex-start; padding-top: 2px; }   /* 标签与查看态同一高度（实测差 1px） */
/* 编辑态不加上内边距（编辑器严格填满单元格） */
.smart-vxe.rh-tall :deep(.vxe-body--column.cell-editing .vxe-cell) { padding: 0; }
/* 枚举（单选/多选）选中态：锚点换行向下展开成浮层框——放开单元格裁剪并顶对齐，
   边框/阴影由 SelectCellPanel 的 .sel-anchor.closed 自绘（随内容增高） */
.smart-vxe :deep(.vxe-body--column.cell-selected-enum) { position: relative; z-index: 2; overflow: visible; }
.smart-vxe :deep(.vxe-body--column.cell-selected-enum .vxe-cell) { overflow: visible; align-items: flex-start; padding: 0 !important; height: 100%; }
.smart-vxe :deep(.vxe-body--column.cell-selected-enum .vxe-cell--wrapper) { overflow: visible; margin: 0 !important; width: 100%; height: 100%; transform: none !important; }
/* 编辑态：去内边距，编辑器严格填满单元格。编辑边框画在 .vxe-cell 上（它与 td 严格同盒），
   不能画在 el-input__wrapper 上——EP wrapper 是 content-box，height:100%+padding 会高出 2px
   被 .vxe-cell 的 overflow:hidden 各裁 1px（上下边框变细的原因） */
.smart-vxe :deep(.vxe-body--column.cell-editing .vxe-cell) {
  padding: 0; height: 100%; box-shadow: 0 0 0 2px var(--st-primary) inset;
}
.smart-vxe :deep(.vxe-body--column.cell-editing .vxe-cell--wrapper) { height: 100%; }
.smart-vxe :deep(.vxe-body--column.cell-editing .el-input),
.smart-vxe :deep(.vxe-body--column.cell-editing .el-select),
.smart-vxe :deep(.vxe-body--column.cell-editing .el-date-editor.el-input) { width: 100%; height: 100%; }
.smart-vxe :deep(.vxe-body--column.cell-editing .el-input__wrapper),
.smart-vxe :deep(.vxe-body--column.cell-editing .el-select__wrapper) {
  height: 100%; min-height: 0; border-radius: 0; box-sizing: border-box;
  box-shadow: none; background: transparent;   /* 透出 .vxe-cell 上的编辑态边框 */
}
.smart-vxe :deep(.vxe-body--column.cell-editing .el-input__inner) { height: 100%; }
/* 枚举（单选/多选）编辑态：锚点换行向下展开成浮层框（打开下拉时锚点不回单行）——
   放开裁剪、顶对齐、关掉 .vxe-cell 的 inset 边框（改由锚点自绘，随内容增高） */
.smart-vxe :deep(.vxe-body--column.cell-editing-enum) { overflow: visible; position: relative; z-index: 3; }
.smart-vxe :deep(.vxe-body--column.cell-editing-enum .vxe-cell) { overflow: visible; box-shadow: none; align-items: flex-start; }
.smart-vxe :deep(.vxe-body--column.cell-editing-enum .vxe-cell--wrapper) { overflow: visible; height: 100%; min-height: 100%; width: 100%; }
.smart-vxe :deep(.cell-indent) { padding-left: 18px; }
/* 显示态内容整体上移 1px：13px CJK 文字在 36px 行高内半行距分布偏下，光学居中补偿。
   只作用非编辑态——编辑边框画在 .vxe-cell 上、编辑器严格填满单元格，不能跟着移 */
.smart-vxe :deep(.vxe-body--column:not(.cell-editing) .vxe-cell--wrapper) { transform: translateY(-2px); }
.smart-vxe :deep(.vxe-body--column.cell-image) { vertical-align: middle; }
.smart-vxe :deep(.vxe-body--column.cell-image .vxe-cell) { height: var(--image-cell-height); padding-top: 0; padding-bottom: 0; align-items: center; }
.smart-vxe :deep(.vxe-body--column.cell-image .vxe-cell--wrapper) { height: 100%; width: 100%; margin: 0 !important; transform: none !important; align-items: center; }
/* 查看/选中态禁止选中文字（企微式：单击只是选中单元格，双击才进编辑态，编辑器内不受影响） */
.smart-vxe :deep(.vxe-body--column:not(.cell-editing) .vxe-cell) { user-select: none; }
/* 行选 checkbox（设计稿 PixPin_2026-10-15_00-02-56 风格：细边圆角小方框；选中主色底+白勾）。
   复选框列去内边距、内容水平居中（vxe 默认左右 padding 不对称，方框会偏左） */
.smart-vxe :deep(.col-ck .vxe-cell) { padding-left: 0 !important; padding-right: 0 !important; display: flex; align-items: center; justify-content: center; }
.smart-vxe :deep(.col-ck .vxe-cell--wrapper) { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; transform: none !important; }
.smart-vxe :deep(.col-ck .vxe-cell--checkbox) { padding: 0; margin: 0; display: inline-flex; align-items: center; justify-content: center; line-height: 1; }
.smart-vxe :deep(.col-ck .vxe-checkbox--label) { display: none; }
.smart-vxe :deep(.vxe-checkbox--icon) {
  font-size: 0;   /* 隐藏 vxe 图标字体的字形，自绘方框 */
  display: inline-block;   /* inline 元素不吃 width/height，必须转 inline-block */
  vertical-align: middle;
  width: 15px; height: 15px; box-sizing: border-box; position: relative;
  border: 1px solid var(--el-border-color-dark); border-radius: 3px; background: #fff;
  transition: background-color .15s, border-color .15s;
}
.smart-vxe :deep(.vxe-cell--checkbox:hover .vxe-checkbox--icon) { border-color: var(--st-primary); }
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked-fill),
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked),
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate-fill),
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate) {
  background: var(--st-primary); border-color: var(--st-primary);
}
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked-fill)::after,
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-checked)::after {
  /* 勾以方框中心定位（固定 left/top 偏移在不同缩放下会偏） */
  content: ''; position: absolute; left: 50%; top: 50%; width: 3.5px; height: 7.5px; box-sizing: content-box;
  border: solid #fff; border-width: 0 1.6px 1.6px 0; transform: translate(-50%, -62%) rotate(45deg);
}
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate-fill)::after,
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate)::after {
  content: ''; position: absolute; left: 50%; top: 50%; width: 7px; height: 1.6px; background: #fff; transform: translate(-50%, -50%);
}
/* 表头单元格统一灰色（含 # 列；字段名/图标的样式由 FieldHeader 自己管，这里不覆盖避免优先级打架） */
.smart-vxe :deep(.vxe-header--column) { font-size: 13px; color: var(--st-head-text); background-color: #fff; user-select: none; }   /* 表头文字不可选中 */
.smart-vxe :deep(.vxe-table--scroll-y-top-corner) { background-color: #fff; }
/* 表头（参照 表头样式.png）：白底，hover 整格浅灰；插槽内容撑满单元格宽，字段名可换行 */
.smart-vxe :deep(.vxe-header--column:hover) { background-color: #F2F3F5; }
/* 右内边距 6px：列头下拉按钮距单元格右边 6px，与单元格单选/多选的下拉按钮（.sel-anchor .chev，right 4 + 边框 2）一致 */
.smart-vxe :deep(.vxe-header--column .vxe-cell) { padding: 6px 6px 6px 6px; box-sizing: border-box; }
.smart-vxe :deep(.vxe-header--column .vxe-cell--wrapper) { width: 100%; min-width: 0; }
/* 不裁剪：字段名自身 line-clamp 控制行数；若在这里 overflow:hidden，24px 的下拉按钮会被单行文字高度（20px）裁掉上下边 */
.smart-vxe :deep(.vxe-header--column .vxe-cell--title) { display: block; flex: 1; width: 100%; min-width: 0; overflow: visible; }
.smart-vxe :deep(.vxe-header--column .vxe-cell--title > span) { display: block; width: 100%; }
/* 有编组时纵跨两层的散列字段：顶对齐（首行与编组标题同一水平线，44px 层高 → 上内边距 12） */
.smart-vxe :deep(.vxe-header--column.th-span) { vertical-align: top; }
.smart-vxe :deep(.vxe-header--column.th-span .vxe-cell) { align-items: flex-start; padding-top: 11px; }
.smart-vxe :deep(.vxe-header--column.th-utility) { vertical-align: top; }
.smart-vxe :deep(.vxe-header--column.th-utility .vxe-cell) {
  height: var(--header-row-height); min-height: var(--header-row-height) !important;
  display: flex; align-items: center; justify-content: center; padding-top: 0; padding-bottom: 0;
}
.smart-vxe :deep(.vxe-header--column.th-utility-grouped .vxe-cell) { transform: translateY(2.5px); }
.smart-vxe :deep(.vxe-header--column.th-utility.col-ck .vxe-cell--title),
.smart-vxe :deep(.vxe-header--column.th-utility.col-ck .vxe-cell--title > span) {
  display: flex; align-items: center; justify-content: center; line-height: 1;
}
/* 列头 / 编组下拉按钮：hover 列头时出现；单击选中的字段列持续显示 */
.smart-vxe :deep(.vxe-header--column:hover .head-menu),
.smart-vxe :deep(.vxe-header--column.th-col-selected:not(.sel-member) .head-menu),
.smart-vxe :deep(.vxe-header--column:hover .cg-caret),
.smart-vxe :deep(.vxe-header--column.th-col-selected .cg-caret) { visibility: visible; }
/* 整列选中（单击表头）：浅蓝底 + 主色描边框住整列（表头顶边 → 统计行底边） */
/* 选中整组（单击编组表头）时同一套样式框住组头 + 全部成员列。
   四条边按 sel-l/sel-r/sel-t/sel-b 分别打开（整组只在外沿画线，组内列之间不画） */
.smart-vxe :deep(.th-col-selected),
.smart-vxe :deep(.col-selected),
.smart-vxe :deep(.tf-col-selected) {
  --cs-l: 0px; --cs-r: 0px; --cs-t: 0px; --cs-b: 0px; }
.smart-vxe :deep(.sel-l) { --cs-l: 1px; }
.smart-vxe :deep(.sel-r) { --cs-r: 1px; }
.smart-vxe :deep(.sel-t) { --cs-t: 1px; }
.smart-vxe :deep(.sel-b) { --cs-b: 1px; }
/* 选中底色 = 在原底色上盖一层半透明主色（::before 贴膜），而不是替换底色：填色（td 内联 background-color）选中后
   仍可见、只是泛蓝（替换会把填色盖掉，参照 PixPin_2026-10-18_00-57-11）。不用 background-image：vxe 用背景渐变画单元格
   边线并设了 background-size，叠加的渐变会被压成 1px 细线、还会冲掉边线。白底上叠出的颜色即原来的 #EEF3FD / #E9EFFC */
.smart-vxe :deep(.vxe-header--column.th-col-selected),
.smart-vxe :deep(.vxe-body--column.col-selected),
.smart-vxe :deep(.vxe-footer--column.tf-col-selected) { position: relative; }
.smart-vxe :deep(.vxe-header--column.th-col-selected)::before,
.smart-vxe :deep(.vxe-body--column.col-selected)::before,
.smart-vxe :deep(.vxe-footer--column.tf-col-selected)::before {
  content: ''; position: absolute; inset: 0; pointer-events: none; background: rgba(46, 107, 230, .08);
  box-sizing: border-box; border-style: solid; border-color: var(--st-primary);
  border-width: var(--cs-t) var(--cs-r) var(--cs-b) var(--cs-l); }
.smart-vxe :deep(.vxe-header--column.th-col-selected)::before { background: rgba(46, 107, 230, .105); }
/* 表头、数据行、统计行统一用 1px border 绘制；首尾轮廓整体内缩，侧边不会突出。 */
.smart-vxe :deep(.vxe-header--row:first-child .vxe-header--column.th-col-selected.sel-t)::before { top: 1px; }
.smart-vxe :deep(.vxe-footer--column.tf-col-selected.sel-b)::before { bottom: 1px; }
.smart-vxe :deep(.vxe-header--column.th-col-selected:hover) { background-color: #fff; }   /* 不叠表头 hover 灰（表头填色是内联样式，不受影响） */
/* 编组组头：标题居中，下拉钉在右侧 */
:deep(.colgroup-title) { display: flex; align-items: center; justify-content: center; position: relative; width: 100%; min-height: 22px; }
/* 编组名与字段名同款：13px 粗体灰 */
:deep(.colgroup-title .cg-name) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 28px;
  font-size: 13px; line-height: 20px; font-weight: 600; color: var(--st-head-text); }
/* 编组下拉：与字段列头一致——默认隐藏，hover 列头出现灰三角，hover 按钮出现浅灰圆角底 */
:deep(.colgroup-title .cg-caret) { position: absolute; right: 0; top: 50%; transform: translateY(-50%); visibility: hidden; background: transparent; }
:deep(.colgroup-title .cg-caret:hover) { background: #E6E8E8; }
/* 统计行（设计稿 PixPin_2026-10-15_19-57-43）：单元格整格可点，hover 浅灰底；
   已配置列两行（方式名小灰字 + 数值右对齐）；未配置列 hover 浮现「统计 ▾」 */
.smart-vxe :deep(.vxe-footer--column) { cursor: pointer; }
.smart-vxe :deep(.vxe-footer--column .vxe-cell) {
  height: 45px; box-sizing: border-box; padding-top: 0; padding-bottom: 0;
}
.smart-vxe :deep(.vxe-footer--column:hover) { background: var(--el-fill-color-light); }
:deep(.footer-stat) { width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; }
:deep(.footer-stat .fs-label) { text-align: right; font-size: 12px; line-height: 18px; color: var(--el-text-color-secondary); }
:deep(.footer-stat .fs-value) { text-align: right; font-size: 15px; line-height: 22px; color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
:deep(.footer-stat .fs-hint) { font-size: 13px; color: var(--el-text-color-secondary); visibility: hidden; }
:deep(.footer-stat:hover .fs-hint) { visibility: visible; }
:deep(.footer-stat .fs-hint) { display: inline-flex; align-items: center; gap: 2px; }
:deep(.filter-dot) { color: var(--st-primary); }
:deep(.sort-mark) { color: var(--st-primary); }
/* 查找命中：浅黄底由 cellFillStyle 内联下发（优先于视图填色）；当前项用金黄描边，放在选中样式之后覆盖蓝框。 */
.smart-vxe :deep(.vxe-body--column.cell-search-match.col-selected)::before { background: transparent; }
.smart-vxe :deep(.vxe-body--column.cell-search-active),
.smart-vxe :deep(.row-last .vxe-body--column.cell-search-active) {
  position: relative; z-index: 4; box-shadow: 0 0 0 2px #FCBA02 inset;
}
.smart-vxe :deep(.row-last .vxe-body--column.cell-search-active)::after { border-color: #FCBA02; }
.smart-vxe :deep(.vxe-body--column.cell-search-active.cell-editing .vxe-cell) { box-shadow: 0 0 0 2px #FCBA02 inset; }
/* 不可编辑提示气泡（teleport 到 body） */
:global(.st-blocked-hint) { position: fixed; z-index: 2200; display: inline-flex; align-items: center; gap: 14px; height: 40px; padding: 0 16px;
  background: #fff; border-radius: 8px; box-shadow: 0 4px 16px rgba(0, 0, 0, .12); font-size: 14px; color: #1F2329; white-space: nowrap; }
:global(.st-blocked-link) { color: var(--st-primary); cursor: pointer; }
/* 展开记录按钮（参照 hover-行.png）：白底细边圆角小方块 + 斜向双箭头，中心压在表格左边框上 */
:global(.st-row-expand) { position: fixed; z-index: 2000; display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; box-sizing: border-box; border: 1px solid var(--st-border); border-radius: 4px;
  background: #fff; color: var(--st-text-2); cursor: pointer; box-shadow: 0 1px 3px rgba(31, 35, 41, .08); }
:global(.st-row-expand:hover) { color: var(--st-primary); }
:global(.st-blocked-link:hover) { text-decoration: underline; }
</style>
