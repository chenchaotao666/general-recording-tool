<template>
  <!-- SmartGrid：智能表网格（vxe-table 封装）。
       flatten 行序列：分组标题行 / 数据行（树形缩进）。添加一行入口在统计行左侧「＋」。
       视图配置（显隐/列序/列宽/冻结/行高/填色）纯前端应用，数据层不动（设计文档 §1.3 原则 1）。 -->
  <div class="smart-grid" @contextmenu.prevent>
    <!-- :key="t_colSig"：列序/列集变化时整表重挂载。vxe 列注册只在挂载时按 DOM 位次进行，
         增量重挂载会与静态列/编组竞态导致顺序错乱，整表重挂载保证按 headerTree 顺序干净注册 -->
    <vxe-table
      ref="gridRef"
      :key="`t_${colSig}`"
      class="smart-vxe"
      :data="gridRows"
      :height="height"
      border
      :row-config="{ height: rowHeightPx, isHover: true, keyField: '__key' }"
      :column-config="{ resizable: true }"
      :scroll-y="{ enabled: true, gt: 100 }"
      :scroll-x="{ enabled: true, gt: 20 }"
      :show-footer="true"
      :footer-method="footerMethod"
      :footer-cell-config="{ height: 52 }"
      :row-class-name="rowClass"
      :cell-class-name="cellClass"
      :cell-style="cellFillStyle"
      :header-cell-style="headerCellStyle"
      :menu-config="menuConfig"
      @cell-click="onCellClick"
      @cell-dblclick="onCellDblClick"
      @menu-click="onMenuClick"
      @checkbox-all="onCheckAll"
      @checkbox-change="onCheckChange"
    >
      <vxe-column type="checkbox" width="36" fixed="left" />
      <vxe-column width="52" fixed="left" title="#" class-name="col-no">
        <template #default="{ row }">
          <span v-if="row.__rowType === 'group'" class="group-toggle" @click.stop="$emit('toggle-group', row.key)">
            {{ collapsedGroups.has(row.key) ? '▸' : '▾' }}
          </span>
          <span v-else class="row-no">{{ row.__no }}</span>
        </template>
        <!-- 统计行左侧：添加一行「＋」（居中，设计稿 PixPin_2026-10-15_20-03-52 位置） -->
        <template #footer>
          <span v-if="!readonly" class="footer-add-btn" title="添加一行" @click.stop="$emit('add-row')">＋</span>
        </template>
      </vxe-column>

      <!-- 编组（两级表头）+ 散列字段列（key 带 colSig：列序变化时重挂载以触发 vxe 重注册） -->
      <template v-for="node in headerTree" :key="`${node.key}:${colSig}`">
        <vxe-colgroup v-if="node.isGroup" :title="node.name" header-align="center">
          <template #header>
            <span class="colgroup-title" title="编组操作" @click.stop="(e) => $emit('group-menu', node.group, e)">
              {{ node.name }} <span class="cg-caret">▾</span>
            </span>
          </template>
          <vxe-column v-for="f in node.fields" :key="f.field_name" :field="f.field_name"
                      :width="colWidths[f.field_name] || 160"
                      :fixed="isFrozen(f.field_name) ? 'left' : undefined">
            <template #header><FieldHeader :field="f" :view="view" @menu="(e) => $emit('field-menu', f, e)" /></template>
            <template #default="{ row }"><CellSlot :row="row" :field="f" /></template>
            <template #footer><FooterCell :field="f" /></template>
          </vxe-column>
        </vxe-colgroup>
        <vxe-column v-else :field="node.field.field_name" :width="colWidths[node.field.field_name] || 160"
                    :fixed="isFrozen(node.field.field_name) ? 'left' : undefined">
          <template #header><FieldHeader :field="node.field" :view="view" @menu="(e) => $emit('field-menu', node.field, e)" /></template>
          <template #default="{ row }"><CellSlot :row="row" :field="node.field" /></template>
          <template #footer><FooterCell :field="node.field" /></template>
        </vxe-column>
      </template>

      <!-- 末尾「+」添加列 -->
      <vxe-column width="48" fixed="right" align="center" header-align="center">
        <template #header>
          <span class="add-col" title="添加一列" @click.stop="(e) => $emit('add-field', e)">＋</span>
        </template>
        <template #default><span /></template>
      </vxe-column>
    </vxe-table>
  </div>
</template>

<script setup>
import { computed, h, nextTick, onBeforeUnmount, ref } from 'vue'
import SmartCell from './SmartCell.vue'
import SmartCellEditor from './SmartCellEditor.vue'
import SelectCellPanel from './SelectCellPanel.vue'
import FieldHeader from './FieldHeader.vue'
import StIcon from '../icons/StIcon.vue'
import { regOf, sortDirectionLabels, STAT_LABELS, formatStatValue, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { evalFillRules, evalRowFill, headerFillColor } from '../../../smart/utils/format.js'

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
})
const emit = defineEmits(['cell-commit', 'add-row', 'cell-menu', 'field-menu', 'toggle-group',
                          'selection-change', 'open-config', 'footer-menu', 'add-option', 'group-menu', 'add-row-in-group'])

const gridRef = ref(null)
const editingCell = ref(null)   // {key, fieldName}

const viewConfig = computed(() => props.view?.config || {})
const rowHeightPx = computed(() => ({ default: 36, medium: 52, tall: 76, extraTall: 100 }[viewConfig.value.rowHeight] || 36))
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
const colSig = computed(() => visibleFields.value.map(f => f.field_name).join(','))

// 两级表头：编组节点 + 散列字段（保持相对顺序，编组内字段聚合到组下）
const headerTree = computed(() => {
  const groups = props.columnGroups.filter(g => (g.field_names || []).length)
  const inGroup = new Set(groups.flatMap(g => g.field_names))
  const nodes = []
  const emittedGroups = new Set()
  for (const f of visibleFields.value) {
    const g = groups.find(x => x.field_names.includes(f.field_name))
    if (!g) {
      nodes.push({ key: f.field_name, isGroup: false, field: f })
    } else if (!emittedGroups.has(g.id)) {
      emittedGroups.add(g.id)
      nodes.push({ key: `g_${g.id}`, isGroup: true, name: g.name, group: g,
                   fields: visibleFields.value.filter(x => g.field_names.includes(x.field_name)) })
    }
  }
  return nodes
})

const isFrozen = (name) => {
  const fz = viewConfig.value.frozenFieldId
  if (!fz) return false
  const list = visibleFields.value.map(f => f.field_name)
  const idx = list.indexOf(fz)
  const mine = list.indexOf(name)
  return idx >= 0 && mine >= 0 && mine <= idx
}

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

const rowClass = ({ row }) => {
  if (row.__rowType === 'group') return `row-group depth-${row.depth}`
  if (row.__rowType === 'group-add') return `row-group-add depth-${row.depth}`
  return ''
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

function cellClass({ row, column }) {
  const cls = []
  if (!row.__rowType && row.__indent > 0 && column.field === visibleFields.value[0]?.field_name) {
    cls.push('cell-indent')
  }
  // 单击选中态（企微式：边框与单元格同大，与编辑态边框同款）。
  // 单选/多选用独立类名：选中框由锚点自绘（标签换行展开时随内容增高），不走 td inset 阴影
  if (selectedCell.value && row.__key === selectedCell.value.key && column.field === selectedCell.value.fieldName) {
    const f = props.fields.find(x => x.field_name === column.field)
    cls.push(['singleSelect', 'multiSelect'].includes(f?.field_type) ? 'cell-selected-enum' : 'cell-selected')
  }
  // 编辑态：去单元格内边距，编辑器与单元格严格同边界。
  // 单选/多选追加 cell-editing-enum：锚点换行展开（同选中态），边框由锚点自绘
  if (editingCell.value && row.__key === editingCell.value.key && column.field === editingCell.value.fieldName) {
    cls.push('cell-editing')
    const f = props.fields.find(x => x.field_name === column.field)
    if (['singleSelect', 'multiSelect'].includes(f?.field_type)) cls.push('cell-editing-enum')
  }
  return cls.join(' ')
}

// 单元格渲染（含填色命中 + 编辑态分发）
function CellSlot(props2) {
  const { row, field } = props2
  const firstField = visibleFields.value[0]?.field_name
  // 组内「+」行：仅首字段列可点（带上该组全部条件预设添加记录）
  if (row.__rowType === 'group-add') {
    if (field.field_name !== firstField || props.readonly) return h('span')
    return h('span', {
      class: 'group-add-btn', title: '在该组内添加一行',
      onClick: (e) => { e.stopPropagation(); emit('add-row-in-group', row.conds) },
    }, [h(StIcon, { name: 'plus', size: 13 })])
  }
  if (row.__rowType === 'group') {
    if (field.field_name !== firstField) {
      const agg = row.aggs?.[field.field_name]
      const aggKind = viewConfig.value.aggregations?.[field.field_name]
      // 聚合值带 ⌄：点击切换统计方式（复用统计行菜单）
      return h('span', {
        class: 'group-agg', title: '点击设置统计方式',
        onClick: (e) => { e.stopPropagation(); emit('footer-menu', field, e) },
      }, agg != null && aggKind
        ? [`${STAT_LABELS[aggKind] || ''} ${formatStatValue(aggKind, agg, field)}`, h(StIcon, { name: 'caret-down', size: 10, class: 'ga-caret' })]
        : '')
    }
    return h('span', { class: 'group-head' }, [
      ...groupValueNodes(row),
      h('span', { class: 'g-count' }, `记录数 ${row.count}`),
    ])
  }
  const isEdit = editingCell.value && editingCell.value.key === row.__key && editingCell.value.fieldName === field.field_name
  if (isEdit && !props.readonly) {
    return h(SmartCellEditor, {
      field, record: row,
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
  // 点下拉按钮或双击锚点 → open 进编辑态（面板展开）
  const isSelEnum = selectedCell.value && selectedCell.value.key === row.__key
    && selectedCell.value.fieldName === field.field_name
    && ['singleSelect', 'multiSelect'].includes(field.field_type)
  if (isSelEnum) {
    return h(SelectCellPanel, {
      field, record: row, frozen: isFrozen(field.field_name), closed: true,
      onCommit: (v) => emit('cell-commit', { row, field, value: v }),   // ✕ 清除直接生效
      onOpen: () => {
        if (props.readonly) return
        selectedCell.value = null
        editingCell.value = { key: row.__key, fieldName: field.field_name }
      },
    })
  }
  // 文本单元格单击选中：用与编辑相同的浮层只读展示全文；双击浮层（enter-edit）再进编辑
  const isSelText = selectedCell.value && selectedCell.value.key === row.__key
    && selectedCell.value.fieldName === field.field_name && field.field_type === 'text'
  if (isSelText) {
    return h(SmartCellEditor, {
      field, record: row, frozen: isFrozen(field.field_name), preview: true,
      onCancel: () => { selectedCell.value = null },
      'onEnter-edit': () => {
        if (props.readonly) return
        selectedCell.value = null
        editingCell.value = { key: row.__key, fieldName: field.field_name }
      },
    })
  }
  // 填色：单元格自身规则优先，整行规则兜底（返回 null 走 cellFillStyle 在 td 级着色）
  const fill = evalFillRules(fillRules.value, field, row[field.field_name]) || rowFills.value.get(row.__key) || null
  const cell = h(SmartCell, { field, record: row, fillColor: fill })
  // 树形父行：首字段列前置子记录计数徽标（树形图标 + N）
  const childN = field.field_name === firstField ? childCounts.value.get(row.id) : 0
  if (childN) {
    return h('span', { class: 'tree-cell' }, [
      h('span', { class: 'tree-badge', title: `${childN} 条子记录` }, [h(StIcon, { name: 'tree', size: 11 }), String(childN)]),
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

// 填色在 td 级着底色（整格铺满，企微式）；SmartCell 的 fillColor 作为内容级兜底保留
function cellFillStyle({ row, column }) {
  if (!row || row.__rowType) return null
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return null
  const fill = evalFillRules(fillRules.value, f, row[f.field_name]) || rowFills.value.get(row.__key) || null
  return fill ? { backgroundColor: fill } : null
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
    children.push(h('div', { class: 'fs-hint' }, ['统计', h('span', { class: 'fs-caret' }, ' ▾')]))
  }
  return h('div', {
    class: 'footer-stat', title: '点击设置统计方式',
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
let lastClick = { key: null, fieldName: null, t: 0 }   // 自检测双击用

function onCellClick({ row, column }) {
  if (props.readonly) return
  if (!row || row.__rowType) return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f) return
  if (IMMEDIATE.includes(f.field_type)) {
    emit('cell-commit', { row, field: f, value: !row[f.field_name] })
    return
  }
  // 自检测双击：同一单元格 400ms 内的第二击直接进编辑。原生 dblclick 不可靠——
  // 第一击后选中态锚点/预览浮层会替换单元格 DOM，两次点击落在不同元素上时 Chrome 不合成 dblclick
  const now = Date.now()
  const isSecond = lastClick.key === row.__key && lastClick.fieldName === f.field_name && now - lastClick.t < 400
  lastClick = isSecond ? { key: null, fieldName: null, t: 0 } : { key: row.__key, fieldName: f.field_name, t: now }
  if (isSecond) {
    selectedCell.value = null
    editingCell.value = { key: row.__key, fieldName: f.field_name }
    return
  }
  // 单击只做选中，进入编辑只能通过双击（或选中态锚点上的 ▼/双击）
  selectedCell.value = { key: row.__key, fieldName: f.field_name }
}

function onCellDblClick({ row, column }) {
  if (props.readonly) return
  if (!row || row.__rowType) return
  const f = props.fields.find(x => x.field_name === column.field)
  if (!f || IMMEDIATE.includes(f.field_type)) return   // checkbox 单击已切换，无需编辑态
  selectedCell.value = null   // 编辑态即脱离选中态
  editingCell.value = { key: row.__key, fieldName: f.field_name }
}

// Esc 取消选中（编辑态的 Esc 由编辑器自身处理）
function onDocKeydown(e) {
  if (e.key === 'Escape' && selectedCell.value && !editingCell.value) {
    selectedCell.value = null
    // vxe 的 cell-class-name 只在渲染周期重算：Esc 清选中不走数据流，手动触发列重渲染
    gridRef.value?.refreshColumn?.()
  }
}

// 点外部取消选中：目标在选中单元格（含枚举锚点展开区）或文本预览浮层内不动，其余一律清选中。
// 用 mousedown 而不是 click：与 vxe 的 cell-click 错开时序，点其他单元格时先清旧、再由 click 落新选中
function onDocMouseDown(e) {
  if (!selectedCell.value || editingCell.value) return
  if (e.target.closest?.('td.cell-selected, td.cell-selected-enum')) return
  if (e.target.closest?.('.cell-overlay')) return   // 文本预览浮层 teleport 在 body，它自己管外部关闭
  selectedCell.value = null
  gridRef.value?.refreshColumn?.()
}

// vxe 原生右键菜单（menu-config；cell-contextmenu 事件在 v4 不对外暴露）
const menuConfig = computed(() => ({
  body: {
    options: [[
      { code: 'expand', name: '展开记录' },
      { code: 'only', name: '只看此内容' },
      { code: 'exclude', name: '不看此内容' },
      { code: 'duplicate', name: '创建副本' },
      { code: 'add-child', name: '添加子记录' },
      { code: 'delete', name: '删除', className: 'ctx-danger' },
    ]],
    visibleMethod: ({ row }) => !!row && !row.__rowType,   // 组标题行/加行不出菜单
  },
}))

function onMenuClick({ row, column, menu }) {
  if (!row || row.__rowType || !menu) return
  const f = props.fields.find(x => x.field_name === column.field)
  emit('cell-menu', { row, field: f, cmd: menu.code })
}

function onCheckAll({ checked }) { emit('selection-change', checked ? dataRowSelection() : []) }
function onCheckChange() { emit('selection-change', dataRowSelection()) }
function dataRowSelection() {
  const recs = gridRef.value?.getCheckboxRecords?.() || []
  return recs.filter(r => !r.__rowType)
}

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onDocKeydown)
  document.removeEventListener('mousedown', onDocMouseDown)
})

document.addEventListener('keydown', onDocKeydown)
document.addEventListener('mousedown', onDocMouseDown)

defineExpose({ clearEditing: () => { editingCell.value = null; selectedCell.value = null } })
</script>

<style scoped>
.smart-grid { width: 100%; }
.add-col { display: block; width: 100%; text-align: center; color: var(--st-text-3); font-weight: 600; cursor: pointer; font-size: 15px; }
/* 末尾添加列：浅灰底方块 + 灰「＋」（对齐参照 添加一列-按钮.png） */
.smart-vxe :deep(.vxe-header--column:has(.add-col)) { background: var(--st-bg-canvas); }
/* 统计行左侧的添加一行「＋」：单元格内居中、整格可点、hover 主色 */
.footer-add-btn {
  display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;
  cursor: pointer; color: var(--el-text-color-regular); font-size: 16px; user-select: none;
}
.footer-add-btn:hover { color: var(--st-primary); }
.group-toggle { cursor: pointer; color: var(--el-text-color-secondary); user-select: none; }
.row-no { color: var(--el-text-color-placeholder); font-size: 12px; }
.group-head { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
/* 分组头：分组值彩色 chip（枚举）+ 记录数灰字（对齐参照 分组-1个字段.png） */
.gv-chip { border-radius: 4px; padding: 1px 8px; font-size: 12px; font-weight: 500; }
.gv-text { font-weight: 600; }
.gv-empty { color: var(--st-text-3); font-weight: 400; }
.g-count { font-size: 12px; color: var(--st-text-3); font-weight: 400; }
.group-agg { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: var(--el-text-color-secondary); cursor: pointer; }
.group-agg:hover { color: var(--st-primary); }
.ga-caret { color: var(--st-text-3); }
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
/* 单击选中态：浅蓝底 #EAF2FE + 2px 主色边框（inset 阴影实现，与单元格同大、不占布局），与编辑态边框同款 */
.smart-vxe :deep(.vxe-body--column.cell-selected) {
  box-shadow: 0 0 0 2px var(--st-primary) inset; position: relative; z-index: 1;
  background-color: var(--st-cell-selected);
}
/* 枚举（单选/多选）选中态：锚点换行向下展开成浮层框——放开单元格裁剪并顶对齐，
   边框/阴影由 SelectCellPanel 的 .sel-anchor.closed 自绘（随内容增高） */
.smart-vxe :deep(.vxe-body--column.cell-selected-enum) { position: relative; z-index: 2; overflow: visible; }
.smart-vxe :deep(.vxe-body--column.cell-selected-enum .vxe-cell) { overflow: visible; align-items: flex-start; }
.smart-vxe :deep(.vxe-body--column.cell-selected-enum .vxe-cell--wrapper) { overflow: visible; margin: 0; width: 100%; height: 100%; }
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
/* 查看/选中态禁止选中文字（企微式：单击只是选中单元格，双击才进编辑态，编辑器内不受影响） */
.smart-vxe :deep(.vxe-body--column:not(.cell-editing) .vxe-cell) { user-select: none; }
/* 行选 checkbox（设计稿 PixPin_2026-10-15_00-02-56 风格：细边圆角小方框；选中主色底+白勾） */
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
  content: ''; position: absolute; left: 4px; top: 1px; width: 4px; height: 8px;
  border: solid #fff; border-width: 0 1.6px 1.6px 0; transform: rotate(45deg);
}
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate-fill)::after,
.smart-vxe :deep(.vxe-checkbox--icon.vxe-table-icon-checkbox-indeterminate)::after {
  content: ''; position: absolute; left: 3px; top: 6px; width: 7px; height: 1.6px; background: #fff;
}
/* 表头单元格统一灰色（含 # 列；字段名/图标的样式由 FieldHeader 自己管，这里不覆盖避免优先级打架） */
.smart-vxe :deep(.vxe-header--column) { font-size: 13px; color: var(--el-text-color-secondary); }
:deep(.field-head) { display: inline-flex; align-items: center; gap: 4px; width: 100%; cursor: default; }
/* 编组组头：居中标题 + ▾（点击出编组操作菜单） */
:deep(.colgroup-title) { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
:deep(.colgroup-title .cg-caret) { color: var(--el-text-color-placeholder); font-size: 10px; }
:deep(.colgroup-title:hover .cg-caret) { color: var(--st-primary); }
/* 统计行（设计稿 PixPin_2026-10-15_19-57-43）：单元格整格可点，hover 浅灰底；
   已配置列两行（方式名小灰字 + 数值右对齐）；未配置列 hover 浮现「统计 ▾」 */
.smart-vxe :deep(.vxe-footer--column) { cursor: pointer; }
.smart-vxe :deep(.vxe-footer--column:hover) { background: var(--el-fill-color-light); }
:deep(.footer-stat) { width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; }
:deep(.footer-stat .fs-label) { text-align: right; font-size: 12px; line-height: 18px; color: var(--el-text-color-secondary); }
:deep(.footer-stat .fs-value) { text-align: right; font-size: 15px; line-height: 22px; color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
:deep(.footer-stat .fs-hint) { font-size: 13px; color: var(--el-text-color-secondary); visibility: hidden; }
:deep(.footer-stat:hover .fs-hint) { visibility: visible; }
:deep(.footer-stat .fs-caret) { color: var(--el-text-color-placeholder); font-size: 11px; }
:deep(.filter-dot) { color: var(--st-primary); }
:deep(.sort-mark) { color: var(--st-primary); }
:deep(.head-menu) { margin-left: auto; color: var(--el-text-color-placeholder); padding: 0 2px; cursor: pointer; }
:deep(.head-menu:hover) { color: var(--st-primary); }
</style>
